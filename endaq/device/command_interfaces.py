"""
Command interfaces: the mechanisms that communicate with
and control the recording device.
"""

import calendar
from copy import deepcopy
from datetime import datetime
import errno
import os.path
import shutil
import sys
from time import sleep, time, struct_time
from typing import Any, AnyStr, ByteString, Dict, Optional, Tuple, Union, Callable, TYPE_CHECKING
import warnings

import logging
logger = logging.getLogger('endaq.device')

from ebmlite import loadSchema
import serial
import serial.tools.list_ports

from .exceptions import DeviceError, CommandError, DeviceTimeout, UnsupportedFeature
from .hdlc import hdlc_decode, hdlc_encode, HDLC_BREAK_CHAR
from .exceptions import CRCError
from .types import Epoch
from . import response_codes
from .response_codes import *

if sys.platform == 'darwin':
    from . import macos as os_specific
elif 'win' in sys.platform:
    from . import win as os_specific
elif sys.platform == 'linux':
    from . import linux as os_specific

if TYPE_CHECKING:
    from .base import Recorder


# ===========================================================================
#
# ===========================================================================


class CommandInterface:
    """
    Base class for command interfaces, the mechanism that communicates with
    and controls the recording device.

    :ivar timeout: The underlying communication medium's response timeout (in
        seconds). This is not the same as the timeout for individual commands.
        Not used by all interface types.
    :ivar status: The last reported device status. Not available on all
        interface types. A tuple containing the status code and a
        status message string (optional).
    """

    # Default maximum encoded command length (bytes). Only applicable to
    # certain interfaces.
    DEFAULT_MAX_COMMAND_SIZE = None


    def __init__(self,
                 device: "Recorder"):
        """ `CommandInterface` instances are rarely (if ever) explicitly
            created; the parent `Recorder` object will create an instance of
            the appropriate `CommandInterface` subclass when its `command`
            property is first accessed.

            :param device: The Recorder to which to interface.
        """
        self.schema = loadSchema('command-response.xml')

        self.device = device
        self.index: int = 0

        # The communication timeout (in seconds).
        self.timeout: Union[int, float] = 1

        # Last command sent: timestamp and a copy of the command (dict)
        self.lastCommand: Tuple[Optional[float], Optional[dict]] = (None, None)

        # Last reported device status. Not available on all interfaces.
        self.status: Tuple[Optional[int], Optional[str]] = (None, None)

        # Some interfaces (i.e. serial) have a maximum packet size.
        self.maxCommandSize = self.DEFAULT_MAX_COMMAND_SIZE


    def __del__(self):
        # Destructor; does a bit of cleanup. Just in case.
        self.close()


    @classmethod
    def hasInterface(cls, device: "Recorder") -> bool:
        """
        Determine if a device supports this `CommandInterface` type.

        :param device: The recorder to check.
        :return: `True` if the device supports the interface.
        """
        raise NotImplementedError


    @property
    def available(self) -> bool:
        """ Is the command interface available and able to accept commands? """
        return self.device and self.device.available


    @property
    def canCopyFirmware(self) -> bool:
        """ Can the device get new firmware/userpage from a file? """
        # Modern devices can update firmware via files, assume True as default.
        return self.device and self.device.available


    @property
    def canRecord(self) -> bool:
        """ Can the device record on command? """
        # Modern devices can record on command, assume True as default
        return self.device and not self.device.isVirtual


    def resetConnection(self) -> bool:
        """
        Reset the interface. Only applicable to subclasses with a persistent
        connection. Fails silently.

        :return: `True` if the connection was reset (or the interface type
            has no persistent connection).
        """
        return True


    def close(self) -> bool:
        """
        Close the interface. Only applicable to subclasses with a persistent
        connection (e.g., `SerialCommandInterface`). Fails silently.

        :return: `True` if the connection was reset (or the interface type
            has no persistent connection).
        """
        return True


    def _encode(self, data: dict,
                checkSize: bool = True) -> Union[bytearray, bytes]:
        """
        Prepare a packet of command data for transmission, doing any
        preparation required by the interface's medium.

        :param data: The unencoded command `dict`.
        :param checkSize: If `False`, skip the check that the length of the
            encoded command is not greater than the device's maximum.
        :return: The encoded command data, with any class-specific
            wrapping or other preparations.
        """
        ebml = self.schema.encodes(data, headers=False)

        if checkSize and self.maxCommandSize is not None and len(ebml) > self.maxCommandSize:
            raise CommandError("Command too large ({}); max size is {}".format(
                    len(ebml), self.maxCommandSize))

        return ebml


    def _decode(self, packet: ByteString) -> dict:
        """
        Translate a response packet (EBML) into a dictionary.

        :param packet: A packet of response data, in EBML with possibly
            additional coding (varying by interface type).
        :return: The response, as nested dictionaries.
        """
        try:
            return self.schema.loads(packet).dump()

        # ebmlite decoding errors generated by bad data are most likely to
        # raise IOError exceptions
        # FUTURE: Catch correct exception type after ebmlite changes (as proposed)
        except IOError as err:
            # Most common bad data error: invalid ID length
            if 'Invalid length' not in str(err):
                raise

            raise CommandError('Response from device could not be decoded ({})'.format(err))


    # =======================================================================
    # The actual command sending and response receiving.
    # =======================================================================

    def _encodeResponseCodes(self,
                             response: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """ Convert any known response codes to their corresponding enum. For
            generating more human-readable output. Invalid enum values are
            not changed.

            :param response: The response dictionary to be returned with
                enums instead of integer response codes. Note that this
                gets modified in-place!
            :return: The modified `response` dictionary (it is modified
                in place, but as a convenience, it is also returned).
        """
        if not response:
            return

        for name, code in [(k, v) for k, v in response.items()
                           if k in response_codes.__dict__]:
            try:
                response[name] = response_codes.__dict__[name](code)
            except (AttributeError, TypeError):
                logger.debug('Received unknown {}: {}'.format(name, code))
                pass

        return response


    def _writeCommand(self, packet: ByteString) -> int:
        """
        Send an encoded EBMLCommand element. This is a low-level write; the
        data should include any transport-specific packaging. It generally
        should not be used directly.

        :param packet: An encoded EBMLCommand element.
        :return: The number of bytes written.
        """
        raise NotImplementedError


    def _readResponse(self,
                      timeout: Optional[Union[int, float]] = None,
                      callback: Optional[Callable] = None) -> Union[None, dict]:
        """
        Wait for and retrieve the response to a serial command. Does not do any
        processing other than (attempting to) decode the EBML payload.

        :param timeout: Time (in seconds) to wait for a valid response before
            raising a `DeviceTimeout` exception. `None` or -1 will wait
            indefinitely.
        :param callback: A function to call each response-checking
            cycle. If the callback returns `True`, the wait for a response
            will be cancelled. The callback function should require no
            arguments.
        :return: A `dict` of response data, or `None` if `callback` caused
            the process to cancel.
        """
        raise NotImplementedError


    def _getTime(self,
                 pause: bool = True) -> Tuple[Epoch, Epoch]:
        """
        Read the date/time from the device. Implemented in the interface
        because the method differs significantly between file-based and other
        types (e.g. serial).

        Must be implemented in every subclass.

        :param pause: If `True` (default), the system waits until a
            whole-numbered second before getting the clock. This may
            improve accuracy across multiple recorders, but may take up
            to a second to run.
        :return: The system time (float) and the device time (integer).
            Both are epoch (UNIX) time (seconds since 1970-01-01T00:00:00).
        """
        raise NotImplementedError


    def _setTime(self,
                 t: Optional[int] = None,
                 pause: bool = True) -> Tuple[Epoch, Epoch]:
        """
        Called by `Recorder.setTime()`.

        Set a recorder's date/time. A variety of standard time types are
        accepted. Note that the minimum unit of time is the whole second.
        Implemented in the interface because the method differs significantly
        between file-based and other types (e.g. serial), and it is
        time-critical.

        Must be implemented in every subclass.

        :param t: The time to write, as seconds since the epoch. The
            current time  (from the host) is used if `None` (default).
        :param pause: If `True` (default), the system waits until a
            whole-numbered second before setting the clock. This may
            improve accuracy across multiple recorders, but may take up
            to a second to run. Not applicable if a specific time is
            provided (i.e. `t` is not `None`).
        :return: The system time (float) and time that was set (integer).
            Both are UNIX epoch time (seconds since 1970-01-01T00:00:00).
        """
        raise NotImplementedError


    def getTime(self,
                epoch: bool = True) -> Union[Tuple[datetime, datetime], Tuple[Epoch, Epoch]]:
        """ Read the date/time from the device. Also returns the current system
            time for comparison.

            :param epoch: If `True`, return the date/time as integer seconds
                since the epoch ('Unix time'). If `False`, return a Python
                `datetime.datetime` object.
            :return: The system time and the device time. Both are UTC.
        """
        with self.device._busy:
            sysTime, devTime = self._getTime(pause=False)

        if epoch:
            return sysTime, devTime

        return (datetime.utcfromtimestamp(sysTime),
                datetime.utcfromtimestamp(devTime))


    def setTime(self, t: Union[Epoch, datetime, struct_time, tuple, None] = None,
                pause: bool = True,
                retries: int = 1) -> Tuple[Epoch, Epoch]:
        """ Set a recorder's date/time. A variety of standard time types are
            accepted. Note that the minimum unit of time is the whole second.

            :param t: The time to write, as either seconds since the epoch
                (i.e. 'Unix time'), `datetime.datetime` or a UTC
                `time.struct_time`. The current time  (from the host) is used
                if `None` (default).
            :param pause: If `True` (default), the system waits until a
                whole-numbered second before setting the clock. This may
                improve accuracy across multiple recorders, but may take up
                to a second to run. Not applicable if a specific time is
                provided (i.e. `t` is not `None`).
            :param retries: The number of attempts to make, should the first
                fail. Although rare, random filesystem things can potentially
                cause hiccups.
            :return: The system time (float) and time that was set (integer).
                Both are UNIX epoch time (seconds since 1970-01-01T00:00:00).
        """
        if t is not None:
            pause = False
            if isinstance(t, datetime):
                t = calendar.timegm(t.timetuple())
            elif isinstance(t, (struct_time, tuple)):
                t = calendar.timegm(t)
            else:
                t = int(t)

        with self.device._busy:
            try:
                return self._setTime(t, pause=pause)
            except IOError:
                if retries > 0:
                    sleep(.5)
                    return self.setTime(pause=pause, retries=retries - 1)
                else:
                    raise


    def getClockDrift(self,
                      pause: bool = True,
                      retries: int = 1) -> float:
        """ Calculate how far the recorder's clock has drifted from the system
            time.

            :param pause: If `True` (default), the system waits until a
                whole-numbered second before reading the device's clock. This
                may improve accuracy since the device's realtime clock is in
                integer seconds.
            :param retries: The number of attempts to make, should the first
                fail. Random filesystem things can potentially cause hiccups.
            :return: The length of the drift, in seconds.
        """
        with self.device._busy:
            try:
                sysTime, devTime = self._getTime(pause=True)
                return sysTime - devTime
            except IOError:
                if retries > 0:
                    sleep(.25)
                    return self.getClockDrift(pause=pause, retries=retries - 1)
                else:
                    raise


    def _sendCommand(self,
                     cmd: dict,
                     response: bool = True,
                     timeout: Union[int, float] = 10,
                     interval: float = .25,
                     index: bool = True,
                     callback: Optional[Callable] = None) -> Union[None, dict]:
        """ Send a raw command to the device and (optionally) retrieve the
            response.

            :param cmd: A dictionary representing a command, with keys matching
                the names of EBML elements.
            :param response: If `True`, wait for and return a response.
            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception. `None` or -1 will wait
                indefinitely.
            :param interval: Time (in seconds) between checks for a
                response.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function
                requires no arguments.

            :raise: DeviceTimeout
        """
        raise NotImplementedError


    def _runSimpleCommand(self,
                          cmd: dict,
                          statusCode: int = DeviceStatusCode.RESET_PENDING,
                          timeoutMsg: Optional[str] = None,
                          wait: bool = True,
                          timeout: Union[int, float] = 5,
                          callback: Optional[Callable] = None) -> bool:
        """ Send a command that will cause the device to reset/dismount. No
            response (other than a simple acknowledgement with a
            ``<DeviceStatusCode>``, if the interface type reports one) is
            expected/required.

            :param cmd: The command to execute.
            :param statusCode: The ``<DeviceStatusCode>`` expected in the
                acknowledgement (if the interface supports one).
            :param wait: If `True`, wait for the recorer to respond and/or
                dismount.
            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception. `None` or -1 will wait
                indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :returns: `True` if the command was successful.
        """
        self._sendCommand(cmd, response=False, timeout=timeout, callback=callback)

        # Since no response is expected, a failure to read a response caused
        # by the device resetting will just set self.status to (None, None).
        # Success is self.status[0] == None or the expected status code.
        if self.status[0] is not None and self.status[0] != statusCode:
            return False

        return self.awaitReboot(timeout=timeout if wait else 0,
                                timeoutMsg=timeoutMsg,
                                callback=callback)


    def startRecording(self,
                       timeout: Union[int, float] = 5,
                       callback: Optional[Callable] = None) -> bool:
        """ Start the device recording, if supported.
            Must be implemented in every subclass.

            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception. `None` or -1 will wait
                indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :returns: `True` if the command was successful.
        """
        raise NotImplementedError


    def reset(self,
              timeout: Union[int, float] = 5,
              callback: Optional[Callable] = None) -> bool:
        """ Reset (reboot) the recorder.
            Must be implemented in every subclass.

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately; `None` or -1 will wait
                indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :returns: `True` if the command was successful.
        """
        raise NotImplementedError


    def getBatteryStatus(self,
                         timeout: Union[int, float] = 1,
                         callback: Optional[Callable] = None) -> bool:
        """ Get the status of the recorder's battery. Not supported on all
            devices. Status is returned as a dictionary. The dictionary will
            always contain the key `"hasBattery"`, and if that is `True`,
            it will contain other keys:

            * `"charging"`: (bool) `True` if the battery is charging.
            * `"percentage"`: (bool) `True` if the reported charge
              level is a percentage, or 3 states (0 = empty,
              255 = full, anything else is 'some' charge) of `False`.
            * `"level"`: (int) The current battery charge level.

            If the device is capable of reporting if it is receiving
            external power, the dict will contain `"externalPower"`
            (bool).

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately; `None` or -1 will wait
                indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :return: A dictionary with the parsed battery status.

            :raise UnsupportedFeature: Raised if the device does not
            support the command.
        """
        # Only interfaces that support this method will implement it.
        raise UnsupportedFeature(self, self.getBatteryStatus)


    def ping(self,
             data: Optional[ByteString] = None,
             timeout: Union[int, float] = 5,
             callback: Optional[Callable] = None) -> bytes:
        """ Verify the recorder is present and responding. Not supported on
            all devices.

            :param data: An optional binary payload, returned by the recorder
                verbatim.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately; `None` or -1 will wait
                indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :return: The received data, which should be identical to the
                data sent.

            :raise UnsupportedFeature: Raised if the device does not
            support the command.
        """
        # Only interfaces that support this method will implement it.
        raise UnsupportedFeature(self, self.ping)


    def blink(self,
              duration: int = 3,
              priority: int = 0,
              a: int = 0b00000111,
              b: int = 0b00000000):
        """ Blink the device's LEDs. This is intended for identifying a
            specific recorder when multiple are plugged into one computer.
            Not supported on all devices.

            Blinking will alternate between patterns `a` and `b` every 0.5
            seconds, continuing for the specified duration. `a` and `b`
            are unsigned 8 bit integers, in which each bit represents one
            of the recorder's LEDs:

            * Bit 0 (LSB): Red
            * Bit 1: Green
            * Bit 2: Blue
            * Bits 3-7: Reserved for future use.

            :param duration: The total duration (in seconds) of the blinking,
                maximum 255. 0 will blink without time limit, stopping when
                the device is disconnected from USB, or when a recording is
                started (trigger or button press).
            :param priority: If 1, the Blink command should take precedence
                over all other device LED sequences. If 0, the Blink command
                should not take precedence over Wi-Fi indications including
                Provisioning, Connecting, and Success/Failure indications,
                but it should take precedence over battery indications.
            :param a: LED pattern 'A'.
            :param b: LED pattern 'B'.
        """
        raise UnsupportedFeature(self, self.blink)


    # =======================================================================
    # Firmware/userpage updating
    #
    # FUTURE: These methods are based on copying FW/userpage files to the
    #   device, and will need refactoring if/when we have another means of
    #   uploading (serial, wireless, etc.)
    # =======================================================================

    def awaitReboot(self,
                    timeout: Optional[Union[int, float]] = None,
                    timeoutMsg: Optional[str] = None,
                    callback: Optional[Callable] = None) -> bool:
        """ Wait for the device to dismount as a drive, indicating it has
            rebooted, started recording, started firmware application, etc.

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately; `None` or -1 will wait
                indefinitely.
            :param timeoutMsg: A command-specific message to use when raising
                a `DeviceTimeout` exception.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :return: `True` if the device unmounted. `False` if it is a
                virtual device, or the wait was cancelled by the callback.
        """
        if self.device.isVirtual or self.device.path is None:
            return False

        if timeout == 0:
            return not self.device.available

        with self.device._busy:
            timeout = -1 if timeout is None else timeout
            deadline = time() + timeout
            while timeout < 0 or time() < deadline:
                if callback is not None and callback():
                    return False
                elif not self.device.available:
                    return True
                sleep(0.1)

            timeoutMsg = timeoutMsg or "Timed out waiting for device to disconnect"
            raise DeviceTimeout(timeoutMsg)


    def awaitRemount(self,
                     timeout: Optional[Union[int, float]] = None,
                     timeoutMsg: Optional[str] = None,
                     callback: Optional[Callable] = None) -> bool:
        """ Wait for the device to reappear as a drive, indicating it has
            been reconnected, completed a recording, finished firmware
            application, etc.

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately; `None` or -1 will wait
                indefinitely.
            :param timeoutMsg: A command-specific message to use when raising
                a `DeviceTimeout` exception.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :return: `True` if the device reappeared. `False` if it is a
                virtual device, or the wait was cancelled by the callback.
        """
        if self.device.isVirtual or self.device.path is None:
            return False

        if timeout == 0:
            return self.device.available

        with self.device._busy:
            timeout = -1 if timeout is None else timeout
            deadline = time() + timeout
            while timeout < 0 or time() < deadline:
                if callback is not None and callback():
                    return False
                elif self.device.available:
                    return True
                sleep(0.1)

            timeoutMsg = timeoutMsg or "Timed out waiting for device to remount"
            raise DeviceTimeout(timeoutMsg)


    def _updateAll(self,
                   secure: True,
                   wait: bool = True,
                   timeout: Union[int, float] = 10,
                   callback: Optional[Callable] = None) -> bool:
        """ Send interface-specific update command. Implemented for each
            subclass.

            :param wait: If `True`, wait for the recorer to dismount,
                indicating the update has started.
            :param timeout: Time (in seconds) to wait for the recorder to
                dismount, implying the updates are being applied. 0 will
                return immediately; `None` or -1 will wait indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :returns: `True` if the command was successful.
        """
        raise NotImplementedError


    def _copyUpdateFile(self,
                        filename: Optional[str],
                        dest: str,
                        clean: bool = False):
        """ Copy an update file to the device. If the file aready exists
            on the device it will be overwritten.

            :param filename: The source filename. Can be `None`.
            :param dest: The target filename. Always supplied.
            :param clean: If `True` and `dest` exists, it will be removed,
                even if `filename` is `None`.
            :return: `True` if the `dest` file exists at the end of the
                process, i.e., it was successfully copied, or already exists
                (if `filename` is `None` and not `clean`).
        """
        # filename is checked 2x, before cleaning and before copying, so
        # nothing gets removed if given a bad (non-None) filename.
        if filename:
            clean = True
            if not os.path.isfile(filename):
                raise FileNotFoundError(errno.ENOENT, "File not found", filename)

        if clean and os.path.isfile(dest):
            logger.debug('Removing {}'.format(dest))
            os.remove(dest)

        if filename:
            logger.debug('Copying {} to {}'.format(filename, dest))
            shutil.copyfile(filename, dest)

        # For *NIX systems: sync filesystem to make sure changes 'take'
        if 'sync' in dir(os):
            os.sync()

        return os.path.isfile(dest)


    def updateDevice(self,
                     firmware: Optional[str] = None,
                     userpage: Optional[str] = None,
                     clean: bool = False,
                     timeout: Union[int, float] = 10.0,
                     callback: Optional[Callable] = None) -> bool:
        """ Apply a firmware package and/or device description data update
            to the device. If no filenames are supplied, it will be assumed
            that one or both of the update files have been manually copied
            to the recorder; a `FileNotFound` exception will be raised if
            neither exist on the device.

            :param firmware: The name of the firmware file (typically
                `".pkg"`, or `".bin"` on older devices). If provided, any
                existing firmware update files already on the device will be
                overwritten.
            :param userpage: The name of the "userpage" device description
                file (typically `".bin"`). If provided, any existing
                userpage update files already on the device will be
                overwritten. Warning: userpage data is specific to an
                individual recorder. Do not install a userpage file created
                for a different device!
            :param clean: If `True`, any existing firmware or userpage
                update files will be removed from the device. Used if either
                `firmware` or `userpage` is supplied (but not both).
            :param timeout: Time (in seconds) to wait for the recorder to
                dismount, implying the updates are being applied. 0 will
                return immediately; `None` or -1 will wait indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :returns: `True` if the device rebooted. Note: this does
                not indicate that the updates were successfully applied.
        """
        # Update filenames on device
        fw = os.path.join(self.device.path, self.device._FW_UPDATE_FILE)
        up = os.path.join(self.device.path, self.device._USERPAGE_UPDATE_FILE)
        sig = fw + ".sig"

        fw_ext = os.path.splitext(str(firmware))[-1].lower()
        up_ext = os.path.splitext(str(userpage))[-1].lower()

        keyRev = self.device.getInfo('KeyRev', 0)

        if firmware:
            if fw_ext not in ('.pkg', '.bin'):
                raise TypeError("Firmware update file must be type .pkg or .bin")

            if fw_ext == '.bin':
                if keyRev:
                    raise ValueError(
                            'Cannot apply unencrypted firmware (*.bin) to device '
                            'with encryption; use *.pkg version if available.')

                # HACK: Unencrypted STM32-based firmware has `STM_` prefix
                # FUTURE: Handle in Recorder subclass instead?
                if str(self.device.mcuType).upper().startswith('STM'):
                    fw = os.path.join(os.path.dirname(fw), 'stm_firmware.bin')
                else:
                    fw = os.path.join(os.path.dirname(fw), 'firmware.bin')

        if userpage and up_ext != '.bin':
            raise ValueError("Userpage update file must be type .bin")

        with self.device._busy:
            hasFw = self._copyUpdateFile(firmware, fw, clean)
            hasUp = self._copyUpdateFile(userpage, up, clean)

            if not (hasFw or hasUp):
                raise FileNotFoundError(errno.ENOENT,
                                        "Device has no update files",
                                        os.path.dirname(fw))

            isPkg = hasFw and fw_ext == ".pkg"
            signature = None if firmware is None or not isPkg else firmware + ".sig"

            if isPkg and not self._copyUpdateFile(signature, sig, clean):
                raise FileNotFoundError(errno.ENOENT,
                                        "Firmware signature file not found",
                                        (signature or sig))

            # Use 'secure' if the device FW update is a .pkg, or it has keys installed.
            secure = bool(isPkg or keyRev)

            return self._updateAll(secure=secure, timeout=timeout, callback=callback)


    def setKeys(self, keys: ByteString,
                timeout: Union[int, float] = 5,
                callback: Optional[Callable] = None):
        """ Update the device's key bundle

            :param keys: The key data.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately. `None` or -1 will wait
                indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :return:
        """
        cmd = {'EBMLCommand': {'SetKeys': keys}}
        return self._sendCommand(cmd, timeout=timeout, callback=callback)


    # =======================================================================
    # Wi-Fi
    # =======================================================================

    def setAP(self,
              ssid: str,
              password: Optional[str] = None,
              wait: bool = False,
              timeout: Union[int, float] = 10,
              callback: Optional[Callable] = None):
        """ Quickly set the Wi-Fi access point (router) and password.
            Applicable only to devices with Wi-Fi hardware.

            :param ssid: The SSID (name) of the wireless access point.
            :param password: The access point password.
            :param wait: If `True`, wait until the device reports it is
                connected before returning.
            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
                `None` or -1 will wait indefinitely.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will be
                cancelled. The callback function should require no arguments.
                The `callback` will not be called if `wait` is `False`.
        """
        timeout = -1 if timeout is None else timeout
        deadline = time() + timeout

        cmd = {'SSID': ssid, 'Selected': 1}
        if password is not None:
            cmd['Password'] = password

        with self.device._busy:
            self.setWifi(cmd, timeout=timeout, callback=callback)
            if not wait or timeout == 0:
                return

            while timeout < 0 or time() < deadline:
                if callback is not None and callback():
                    return None

                response = self.queryWifi(timeout=0.5)
                if response:
                    status = response.get('WiFiConnectionStatus')
                    if status == WiFiConnectionStatus.CONNECTED:
                        return
                else:
                    logger.debug('setAP(): got bad queryWifi() response: {!r}'
                                 .format(response))

                sleep(min(timeout, 0.5))

        raise DeviceTimeout('Timed out waiting to connect to AP SSID {}'.format(ssid))


    def setWifi(self,
                wifi_data: dict,
                timeout: Union[int, float] = 10,
                interval: float = 1.25,
                callback: Optional[Callable] = None):
        """ Configure all known Wi-Fi access points. Applicable only
            to devices with Wi-Fi hardware. The data is in the form of a
            list of dictionaries with the following keys:

            * ``"SSID"``: The Wi-Fi access point name (string)
            * ``"Password"``: The access point's password (string, optional)
            * ``"Selected"``: 1 if the device should use this AP, 0 if not

            Note that devices (as of firmware 3.0.17) do not support
            configuring multiple Wi-Fi AP. Consider using
            :meth:`~.endaq.device.command_interfaces.CommandInterface.setAP`
            instead.

            :param wifi_data: The information about the Wi-Fi networks to be
                set on the device.
            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
                `None` or -1 will wait indefinitely.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will be
                cancelled. The callback function should require no arguments.

            :raise UnsupportedFeature: Raised if the device does not
                support Wi-Fi.
        """
        # FUTURE: Ensure that the setting of multiple networks at once behaves
        #  as expected (not currently implemented in FW?)

        if not self.device.hasWifi:
            raise UnsupportedFeature('{!r} has no Wi-Fi adapter'.format(self.device))

        cmd = {'EBMLCommand': {'SetWiFi': {"AP": wifi_data}}}

        self._sendCommand(cmd,
                          response=False,
                          timeout=timeout,
                          interval=interval,
                          callback=callback)


    def queryWifi(self,
                  timeout: Union[int, float] = 10,
                  interval: float = .25,
                  callback: Optional[Callable] = None) -> Union[None, dict]:
        """ Check the current state of the Wi-Fi (if present). Applicable only
            to devices with Wi-Fi hardware.

            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :return: None if no information was recieved, else it will return
                the information from the ``QueryWiFiResponse`` command (this
                return statement is not used anywhere)

            :raise UnsupportedFeature: Raised if the device does not
                support Wi-Fi.
            :raise DeviceTimeout: Raised if 'timeout' seconds have gone by
                without getting a response
        """
        if not self.device.hasWifi:
            raise UnsupportedFeature('{!r} has no Wi-Fi adapter'.format(self.device))

        response = self._sendCommand(
            {'EBMLCommand': {'QueryWiFi': {}}},
            response=True,
            timeout=timeout,
            interval=interval,
            callback=callback)

        if response is None:
            return None

        return self._encodeResponseCodes(response.get('QueryWiFiResponse'))


    def scanWifi(self, 
                 timeout: Union[int, float] = 10,
                 interval: float = .25,
                 callback: Optional[Callable] = None) -> Union[None, list]:
        """ Initiate a scan for Wi-Fi access points (APs). Applicable only
            to devices with Wi-Fi hardware.

            The resluts are returned as a list of dictionaries, one for each
            access point, with keys:

            * ``SSID`` (str): The access point name.
            * ``RSSI`` (int): The AP's signal strength.
            * ``AuthType`` (int): The authentication (security) type.
              Currently, this is either 0 (no authentication) or 1
              (any authentication).
            * ``Known`` (bool): Is this access point known (i.e. has
              a stored password on the device)?
            * ``Selected`` (bool): Is this the currently selected AP?

            :raise DeviceTimeout: Raised if 'timeout' seconds have gone by
                without getting a response

            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will
                be cancelled. The callback function should require no arguments.
            :return: A list of dictionaries, described above.

            :raise UnsupportedFeature: Raised if the device does not
                support Wi-Fi.
        """

        if not self.device.hasWifi:
            raise UnsupportedFeature('{!r} has no Wi-Fi adapter'.format(self.device))

        cmd = {'EBMLCommand': {'WiFiScan': None}}

        response = self._sendCommand(cmd, response=True, timeout=timeout,
                                     interval=interval, callback=callback)

        if response is None:
            return None

        aps = []
        if 'WiFiScanResult' in response:  # If at least 1 Wi-Fi was found during the scan
            for ap in response['WiFiScanResult'].get('AP', []):
                defaults = {'SSID': '', 'RSSI': -1, 'AuthType': 0, 'Known': 0, 'Selected': 0}

                defaults.update(ap)
                defaults['Known'] = bool(defaults['Known'])
                defaults['Selected'] = bool(defaults['Selected'])
                # defaults['RSSI'] = - defaults['RSSI']

                aps.append(defaults)

            return aps


    def updateESP32(self,
                    firmware: str,
                    timeout: Union[int, float] = 10,
                    callback: Optional[Callable] = None):
        """ Update the ESP32 firmware. Applicable only to devices with
            ESP32 Wi-Fi hardware.

            Note: Updating the ESP32 is a long process, typically taking
            up to 4 minutes after calling the function to complete. This
            is normal.

            :param firmware: The name of the ESP32 firmware package (.bin).
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately; `None` or -1 will wait
                indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.

            :raise UnsupportedFeature: Raised if the device does not
                support Wi-Fi via ESP32 hardware.
        """
        # FUTURE: This (and other file-based update) will need refactoring
        #  if/when we have another means of uploading (serial, wireless,
        #  etc.)
        if not self.device.hasWifi or "ESP" not in self.device.hasWifi:
            raise UnsupportedFeature("{!r} does not have an ESP32".format(self.device))

        firmware = os.path.abspath(firmware)

        destination = os.path.abspath(os.path.join(self.device.path,
                                                   self.device._ESP_UPDATE_FILE))
        self._copyUpdateFile(firmware, destination)

        # FUTURE (maybe): Restore `ESPFW` command and destination filename in
        #  payload (in versions <=1.0.7). Not currently implemented in FW.
        payload = {}

        cmd = {'EBMLCommand': {'LegacyESP': payload}}
        return self._runSimpleCommand(cmd, timeout=timeout, callback=callback)


    def getNetworkStatus(self,
                         timeout: Union[int, float] = 10,
                         interval: float = .25,
                         callback: Optional[Callable] = None) -> Union[None, dict]:
        """ Check the device's networking hardware. The response is less
            specific to one interface type (i.e., the results of
            :meth:`~.endaq.device.command_interfaces.CommandInterface.queryWiFi()`).

            The resluts is a dictionary, with keys:

            * ``MACAddress`` (bytes): The unique hardware address of the
                device's network interface (does not change).
            * ``IPV4Address`` (bytes): The device's IP address (typically
                set by the router when the device connects). This will not
                be present if the device is not connected.
            * ``CurrentWiFiStatus`` (int, optional): The Wi-Fi connection
                status. May not be present. Note: this is not the same as the
                ``WiFiConnectionStatus`` in the response returned by
                :meth:`~.endaq.device.command_interfaces.CommandInterface.queryWifi()`.

            :raise DeviceTimeout: Raised if 'timeout' seconds have gone by
                without getting a response

            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
                `None` or -1 will wait indefinitely
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will
                be cancelled. The callback function should require no arguments.
            :return: A list of dictionaries, described above.

            :raise UnsupportedFeature: Raised if the device does not
                support Wi-Fi.
        """
        if not self.device.hasWifi:
            raise UnsupportedFeature('{!r} has no network adapter'.format(self.device))


        response = self._sendCommand({'EBMLCommand': {'NetworkStatus': None}},
                                 response=True,
                                 timeout=timeout,
                                 interval=interval,
                                 callback=callback)

        return self._encodeResponseCodes(response.get('NetworkStatusResponse'))


    def getNetworkAddress(self,
                          timeout: Union[int, float] = 10,
                          interval: float = .25,
                          callback: Optional[Callable] = None
                          ) -> Tuple[Optional[str], Optional[str]]:
        """ Get the device's unique MAC address and its assigned IPv4 address
            as a tuple of human-readable strings (e.g.,
            ``("89:ab:cd:ef", "192.168.1.10")``). If the device is not
            connected, the IP (the second item in the tuple) will be `None`.
            If the device does not have network hardware (Wi-Fi, etc.),
            both the MAC and IP will be `None`; unlike the other network
            related methods, it does not raise an exception if the device
            does not have network hardware.

            :raise DeviceTimeout: Raised if 'timeout' seconds have gone by
                without getting a response

            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
                `None` or -1 will wait indefinitely.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will
                be cancelled. The callback function should require no arguments.
            :return: A two-item tuple containing the device's MAC address
                and IP address. One or both may be `None`, as described
                above.
        """
        if not self.device.hasWifi:
            return None, None

        result = self.getNetworkStatus(timeout, interval, callback) or {}

        mac = result.get('MACAddress', None)
        if mac:
            try:
                if any(mac):
                    mac = ':'.join('{:02X}'.format(b) for b in mac)
                else:
                    mac = None
            except (TypeError, ValueError) as err:
                warnings.warn("{} parsing MAC address: {}"
                              .format(type(err).__name__, err))

        ip = result.get('IPV4Address', None)
        if ip:
            try:
                if any(ip):
                    ip = '.'.join(str(b) for b in ip)
                else:
                    ip = None
            except (TypeError, ValueError) as err:
                warnings.warn("{} parsing IP address: {}"
                              .format(type(err).__name__, err))

        return mac, ip


# ===========================================================================
#
# ===========================================================================

class SerialCommandInterface(CommandInterface):
    """
    A mechanism for sending commands to a recorder via a serial port.

    :ivar status: The last reported device status. Not available on all
        interface types.
    :ivar make_crc: If `True`, generate CRCs for outgoing packets.
    :ivar ignore_crc: If `True`, ignore the CRC on response packets.
    """

    # USB serial port vendor and product IDs, for finding the right device
    USB_IDS = ((0x10C4, 0x0004),  # SiLabs USB Serial, e.g. enDAQ recorders
               (0x0483, 0x4003))  # STM32 USB Serial, e.g. newer enDAQs

    # Default serial port parameters
    SERIAL_PARAMS = dict(baudrate=115200,
                         bytesize=8,
                         parity='N',
                         stopbits=1,
                         timeout=1)

    # Default maximum encoded command length (bytes).
    # FUTURE: The maximum command size will be a child element in
    #  the DEVINFO and should be fetched from it. Default is 128.
    DEFAULT_MAX_COMMAND_SIZE = 128


    def __init__(self,
                 device: 'Recorder',
                 make_crc: bool = True,
                 ignore_crc: bool = False,
                 **serial_kwargs):
        """
        Constructor.

        :param device: The Recorder to which to interface.
        :param make_crc: If `True`, generate CRCs for outgoing packets.
        :param ignore_crc: If `True`, ignore the CRC on response packets.

        If additional keyword arguments are provided, they will be used
        when opening the serial port.
        """
        super().__init__(device)

        self.make_crc = make_crc
        self.ignore_crc = ignore_crc
        self.port = None

        serial_kwargs.pop('port', None)
        self.portArgs = serial_kwargs
        self.portArgs.update(self.SERIAL_PARAMS)

        # Last received response, primarily for debugging. may remove.
        self._lastbuf = None  # Raw binary of previous response, verbatim
        self._response = None  # (timestamp, parsed response)


    @classmethod
    def hasInterface(cls, device: "Recorder") -> bool:
        """ Determine if a device supports this `CommandInterface` type.

            :param device: The recorder to check.
            :return: `True` if the device supports the interface.
        """
        if device.isVirtual:
            return False

        # If the DEVINFO explicitly indicates a serial command interface,
        # trust it.
        if device.getInfo('SerialCommandInterface') is not None:
            return True

        # Some older released FW that supports the serial command interface
        # does not indicate so in the DEVINFO; find the port instead.
        return bool(cls.findSerialPort(device))


    @property
    def available(self) -> bool:
        """ Is the command interface available and able to accept commands? """
        if self.device.isVirtual:
            return False

        # Availability determined by the presence of the serial port.
        try:
            self.getSerialPort()
            return True
        except CommandError as err:
            if 'No serial port found' in str(err):
                return False
            raise


    @classmethod
    def findSerialPort(cls, device: "Recorder") -> Union[None, str]:
        """ Find the path/name/number of a serial port corresponding to a
            given serial number.

            :param device: The recorder to check.
            :return: The corresponding serial port path/name/number, or
                `None` if no matching port is found.
        """
        if device.isVirtual:
            return None

        for p in serial.tools.list_ports.comports():
            # Find valid USB/serial device by vendor/product ID
            # if (p.vid, p.pid) not in cls.USB_IDS:
            #     continue
            try:
                if not p.serial_number:
                    continue
                sn = int(p.serial_number)
                if sn == device.serialInt:
                    return p.device
            except ValueError as err:
                # Probably text in serial number, ignore if so
                if 'invalid literal' not in str(err).lower():
                    raise


    def getSerialPort(self,
                      reset: bool = False,
                      **kwargs) -> Union[None, serial.Serial]:
        """
        Connect to a device's serial port.

        :param reset: If `True`, reset the serial connection if already open.
            Use if the path/number to the device's serial port has changed.
        :return: A `serial.Serial` instance, or `None` if no port matching
            the device can be found.

        Additional keyword arguments will be used when opening the port. Note:
        these will be ignored if the port has already been created and `reset`
        is `False`.
        """
        if self.port:
            try:
                if reset:
                    self.port.close()
                else:
                    if not self.port.is_open:
                        self.port.open()

                    # Sanity check. Will fail if the device reset the port
                    _ = self.port.in_waiting

                    return self.port

            except (IOError, OSError, serial.SerialException):
                # Disconnected device can cause this. Ignore in this case.
                pass

        portname = self.findSerialPort(self.device)

        if not portname:
            self.port = None
            raise CommandError('No serial port found for {}'.format(self.device))

        kwargs.setdefault('timeout', self.timeout)
        params = self.SERIAL_PARAMS.copy()
        params.update(kwargs)

        self.port = serial.Serial(portname, **params)
        return self.port


    # =======================================================================
    # The methods below are the ones shared across subclasses
    # =======================================================================

    def resetConnection(self) -> bool:
        """ Reset the serial connection.

            :return: `True` if the interface connection was reset.
        """
        self.getSerialPort(reset=True)
        return self.port is not None


    def close(self) -> bool:
        """ Close the serial connection.

            :return: `True` if the interface connection has closed, or was
                already closed.
        """
        try:
            if self.port and self.port.is_open:
                self.port.close()
                return not self.port.is_open
        except (IOError, OSError, serial.SerialException) as err:
            # Disconnected device can cause this.
            logger.debug("Ignoring exception when closing {} (probably okay): "
                         "{!r}".format(type(self).__name__, err))
        return True


    def _encode(self,
                data: dict,
                checkSize: bool = True) -> bytearray:
        """
            Generate a serial packet containing EBMLCommand data. Separated from
            sending for use with time-critical functions to minimize latency.

            :param data: The unencoded command `dict`.
            :param checkSize: If `False`, skip the check that the length of the
                encoded command is not greater than the device's maximum.
            :return: A `bytearray` containing the packetized EBMLCommand data.
        """
        ebml = super()._encode(data, checkSize)

        # Header: address 0 (broadcast), EBML data, immediate write.
        packet = bytearray([0x80, 0x26, 0x00, 0x0A])
        packet.extend(ebml)
        packet = hdlc_encode(packet, crc=self.make_crc)
        return packet


    def _decode(self,
                packet: ByteString) -> dict:
        """
            Translate a response packet into a dictionary. Removes additional
            header data and checks the CRC (if the interface's `ignore_crc`
            attribue is `False`) before parsing the binary EBML contents.

            :param packet: A packet of response data.
            :return: The response, as nested dictionaries.
        """
        # Testing note: because response headers differ from commands, this
        # method cannot directly decode a packet created by `encode()`.

        # Messages are Corbus packets:
        # HDLC escaped short header, payload, crc16
        packet = hdlc_decode(packet, ignore_crc=self.ignore_crc)
        if packet.startswith(b'\x81\x00'):
            resultcode = packet[2]
            if resultcode == 0:
                return super()._decode(packet[3:-2])
            else:
                errname = {0x01: "Corbus command failed",
                           0x07: "bad Corbus command"}.get(resultcode, "unknown error")
                raise CommandError("Response header indicated an error (0x{:02x}: {})".format(resultcode, errname))
        else:
            raise CommandError('Response was corrupted or incomplete; did not have expected Corbus header')


    def _writeCommand(self,
                      packet: ByteString) -> int:
        """ Transmit a fully formed packet (addressed, HDLC encoded, etc.)
            via serial. This is a low-level write to the medium and does not
            do the additional housekeeping that `sendCommand()` does;
            typically, it should not be used directly.

            :param packet: The encoded, packetized, binary `EBMLCommand`
                data.
            :return: The number of bytes written.
        """
        port = self.getSerialPort()

        if port.in_waiting:
            logger.debug('Flushing {} bytes from serial input'.format(port.in_waiting))
            port.flushInput()

        return port.write(packet)


    def _readResponse(self,
                      timeout: Optional[float] = None,
                      callback: Optional[Callable] = None) -> Union[None, dict]:
        """
        Wait for and retrieve the response to a serial command. Does not do
        any processing other than (attempting to) decode the EBML payload.

        :param timeout: Time to wait for a valid response. `None` or -1 will
            wait indefinitely.
        :param callback: A function to call each response-checking
            cycle. If the callback returns `True`, the wait for a
            response will be cancelled. The callback function should
            require no arguments.
        :return: A `dict` of response data, or `None` if `callback` caused
            the process to cancel.
        """
        timeout = -1 if timeout is None else timeout
        deadline = time() + timeout

        buf = b''

        while timeout < 0 or time() < deadline:
            if callback is not None and callback():
                return
            if self.port.in_waiting:
                buf += self.port.read()
                self._lastbuf = buf
                if HDLC_BREAK_CHAR in buf:
                    packet, _, buf = buf.partition(HDLC_BREAK_CHAR)
                    if packet.startswith(b'\x81\x00'):
                        response = self._decode(packet)
                        self._response = time(), response
                        if 'EBMLResponse' not in response:
                            logger.warning('Response did not contain an EBMLResponse element')
                        return response.get('EBMLResponse', response)
                    else:
                        # In the future, there might be other devices on the
                        # bus, so a wrong header might be for a different
                        # address. Ignore.
                        logger.debug("Packet incomplete or has wrong header, ignoring")
            else:
                sleep(.01)

        raise TimeoutError("Timeout waiting for response to serial command")


    def _sendCommand(self,
                     cmd: dict,
                     response: bool = True,
                     timeout: Union[int, float] = 10,
                     interval: float = .25,
                     index: bool = True,
                     callback: Optional[Callable] = None) -> Union[None, dict]:
        """ Send a command to the device and (optionally) retrieve the
            response.

            :param cmd: The command data, as a `dict` that can be encoded as
                EBML data.
            :param response: If `True`, return a response. All serial
                commands generate a response; this is primarily for use with
                commands that potentially cause a reset faster than the
                acknowledgement can be read.
            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
                `None` or -1 will wait indefinitely.
            :param interval: Time (in seconds) between checks for a
                response. Not used by the serial interface.
            :param index: If `True` (default), include an incrementing
                'command index' (for matching responses to commands).
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :return: The response dictionary, or `None` if `response` is
                `False`.

            :raise: DeviceTimeout
        """
        timeout = -1 if timeout is None else timeout
        deadline = time() + timeout

        with self.device._busy:
            self.getSerialPort()
            try:
                while True:
                    if 'EBMLCommand' in cmd and index:
                        self.index += 1
                        cmd['EBMLCommand']['CommandIdx'] = self.index

                    packet = self._encode(cmd)
                    self.lastCommand = time(), deepcopy(cmd)
                    self._writeCommand(packet)
            
                    if timeout == 0:
                        return None

                    try:
                        resp = self._readResponse(timeout, callback=callback)
                    except (IOError, serial.SerialException) as err:
                        # Commands that reset can cause the device to close the
                        # port faster than the response can be read. Fail
                        # gracefully if no response is required.
                        if (not isinstance(err, serial.SerialException)
                                and getattr(err, 'errno') != errno.EIO):
                            # Linux (possibly other POSIX) raises IOError EIO (5)
                            # if the port is gone. Raise if other errno.
                            raise
                        if not response:
                            logger.debug('Ignoring anticipated exception because '
                                         'response not required: {!r}'.format(err))
                            self.status = None, None
                            return None
                        else:
                            raise

                    if resp:
                        code = resp.get('DeviceStatusCode', 0)
                        msg = resp.get('DeviceStatusMessage')
                        queueDepth = resp.get('CMDQueueDepth', 1)

                        try:
                            code = DeviceStatusCode(code)
                        except ValueError:
                            logger.debug('Received unknown DeviceStatusCode: {}'.format(code))

                        self.status = code, msg

                        if code < 0:
                            # Raise a CommandError or DeviceError. -20 and -30 refer
                            # to bad commands sent by the user.
                            EXC = CommandError if -30 <= code <= -20 else DeviceError
                            raise EXC(code, msg, self.lastCommand[1])

                        if queueDepth == 0:
                            logger.debug('Command queue full, retrying.')
                        else:
                            respIdx = resp.get('ResponseIdx')
                            if respIdx == self.index:
                                return resp if response else None
                            else:
                                logger.debug('Bad ResponseIdx; expected {}, got {}. '
                                             'Retrying.'.format(self.index, respIdx))
                    else:
                        queueDepth = 1

                    # Failure!
                    if timeout > 0 and time() >= deadline:
                        if queueDepth == 0:
                            raise DeviceTimeout('Timed out waiting for opening in command queue')
                        else:
                            raise DeviceTimeout('Timed out waiting for command response')

            except TimeoutError:
                if not response:
                    logger.debug('Ignoring timeout waiting for response '
                                 'because no response required')
                    self.status = None, None
                    return None
                else:
                    raise

            finally:
                self.port.close()


    def _getTime(self,
                 pause: bool = True,
                 timeout: Union[int, float] = 1) -> Tuple[Epoch, Epoch]:
        """
        Called by `Recorder.getTime()` and `Recorder.getClockDrift()`.

        Read the date/time from the device.

        :param pause: If `True` (default), the system waits until a
            whole-numbered second before getting the clock. This may
            improve accuracy across multiple recorders, but may take up
            to a second to run.
        :return: The system time (float) and the device time (integer).
            Both are epoch (UNIX) time (seconds since 1970-01-01T00:00:00).
        """
        # NOTE: This is implemented here because the method of getting/setting
        #  the time via file vs. via serial differs greatly. Other interfaces
        #  should implement their own as well.

        command = {'EBMLCommand': {'GetClock': {}}}
        with self.device._busy:
            sysTime = t = time()

            if pause:
                while int(t) == int(sysTime):
                    sysTime = time()

            response = self._sendCommand(command, timeout=timeout)
            try:
                dt = response['ClockTime']
                devTime = self.device._TIME_PARSER.unpack_from(dt)[0]
            except KeyError:
                raise CommandError("GetClock response did not contain ClockTime")

        return sysTime, devTime


    def _setTime(self,
                 t: Optional[int] = None,
                 pause: bool = True) -> Tuple[Epoch, Epoch]:
        """
        Called by `Recorder.setTime()`.

        Set a recorder's date/time. A variety of standard time types are
        accepted. Note that the minimum unit of time is the whole second.

        :param t: The time to write, as seconds since the epoch. The
            current time  (from the host) is used if `None` (default).
        :param pause: If `True` (default), the system waits until a
            whole-numbered second before setting the clock. This may
            improve accuracy across multiple recorders, but may take up
            to a second to run. Not applicable if a specific time is
            provided (i.e. `t` is not `None`).
        :return: The system time (float) and time that was set (integer).
            Both are UNIX epoch time (seconds since 1970-01-01T00:00:00).
        """
        if t is None:
            t = time()
            if pause:
                # `pause` will set the time on the next second
                t += 1
        else:
            pause = False

        t = int(t)
        payload = self.device._TIME_PARSER.pack(t)

        t0 = time()
        if pause:
            while t0 < t:
                t0 = time()

        self._sendCommand({'EBMLCommand': {'SetClock': payload}},
                          response=False)

        return t0, t


    def ping(self,
             data: Optional[ByteString] = None,
             timeout: Union[int, float] = 10,
             interval: float = .25,
             callback: Optional[Callable] = None) -> dict:
        """ Verify the recorder is present and responding. Not supported on
            all devices.

            :param data: Optional data, which will be returned verbatim.
            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a
                response.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should require no
                arguments.
            :return: The received data, which should be identical to the
                data sent.
        """
        cmd = {'EBMLCommand': {'SendPing': b'' if data is None else data}}
        response = self._sendCommand(cmd, timeout=timeout, interval=interval,
                                     callback=callback)

        if 'PingReply' not in response:
            raise CommandError('Ping response did not contain a PingReply')

        return response['PingReply']


    def blink(self,
              duration: int = 3,
              priority: int = 0,
              a: int = 0b00000111,
              b: int = 0b00000000):
        """ Blink the device's LEDs. This is intended for identifying a
            specific recorder when multiple are plugged into one computer.
            Not supported on all devices.

            Blinking will alternate between patterns `a` and `b` every 0.5
            seconds, continuing for the specified duration. `a` and `b`
            are unsigned 8 bit integers, in which each bit represents one
            of the recorder's LEDs:
                * Bit 0 (LSB): Red
                * Bit 1: Green
                * Bit 2: Blue
                * Bits 3-7: Reserved for future use.

            :param duration: The total duration (in seconds) of the blinking,
                maximum 255. 0 will blink without time limit, stopping when
                the device is disconnected from USB, or when a recording is
                started (trigger or button press).
            :param priority: If 1, the Blink command should take precedence
                over all other device LED sequences. If 0, the Blink command
                should not take precedence over Wi-Fi indications including
                Provisioning, Connecting, and Success/Failure indications,
                but it should take precedence over battery indications.
            :param a: LED pattern 'A'.
            :param b: LED pattern 'B'.
        """
        payload = bytearray([val & 0xff for val in (duration, priority, a, b)])
        self._sendCommand({'EBMLCommand': {'Blink': payload}}, response=False)


    def getBatteryStatus(self,
                         timeout: Union[int, float] = 1,
                         callback: Optional[Callable] = None) -> Union[dict, None]:
        """ Get the status of the recorder's battery. Not supported on all
            devices.

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should require no
                arguments.
            :return: A dictionary with the parsed battery status. It will
                always contain the key `"hasBattery"`, and if that is `True`,
                it will contain other keys:

                * `"charging"`: (bool)
                * `"percentage"`: (bool) `True` if the reported charge
                    level is a percentage, or 3 states (0 = empty,
                    255 = full, anything else is 'some' charge).
                * `"level"`: (int) The current battery charge level.

                If the device is capable of reporting if it is receiving
                external power, the dict will contain `"externalPower"`
                (bool).
        """
        cmd = {'EBMLCommand': {'GetBattery': {}}}
        response = self._sendCommand(cmd, timeout=timeout,
                                     callback=callback)
        if not response:
            return None
        response = response.get('BatteryState')

        hasBattery = bool(response & 0x8000)
        reply = {'hasBattery': hasBattery}
        if hasBattery:
            reply["charging"] = bool(response & 0x0200)  # bit 9: battery charging
            reply["percentage"] = bool(response & 0x0100)  # bit 8: reports percentage or 0/some/full
            reply["level"] = response & 0x00ff  # Lower 8 bits: battery level

            # External power indicator (bit 14). Indicates external power can
            # be detected (not the same as charging).
            # For future use; bit 14 will always be low until implemented in FW.
            if response & 0x4000:  # bit 14: device can report external power
                reply["externalPower"] = bool(response & 0x2000)

        return reply


    def startRecording(self,
                       wait: bool = True,
                       timeout: Union[int, float] = 5,
                       callback: Optional[Callable] = None) -> bool:
        """ Start the device recording.

            :param wait: If `True`, wait for the recorer to respond and/or
                dismount, indicating the recording has started.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should require no
                arguments.
            :returns: `True` if the command was successful.
        """
        return self._runSimpleCommand({'EBMLCommand': {'RecStart': {}}},
                                      statusCode=DeviceStatusCode.START_PENDING,
                                      timeoutMsg="Timed out waiting for recording to start",
                                      wait=wait,
                                      timeout=timeout,
                                      callback=callback)


    def reset(self,
              wait: bool = True,
              timeout: Union[int, float] = 5,
              callback: Optional[Callable] = None) -> bool:
        """ Reset (reboot) the recorder.

            :param wait: If `True`, wait for the recorer to respond and/or
                dismount, indicating the reset has started.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should require no
                arguments.
            :returns: `True` if the command was successful.
        """
        return self._runSimpleCommand({'EBMLCommand': {'Reset': {}}},
                                      statusCode=DeviceStatusCode.RESET_PENDING,
                                      timeoutMsg="Timed out waiting for device to reset",
                                      wait=wait,
                                      timeout=timeout,
                                      callback=callback)


    def _updateAll(self,
                   secure: bool = True,
                   wait: bool = True,
                   timeout: Union[int, float] = 5,
                   callback: Optional[Callable] = None):
        """ Send the 'secure update all' command, installing any userpage
            and/or firmware update files copied to the device.

            :param wait: If `True`, wait for the recorer to dismount,
                indicating the update has started.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately. `None` or -1 will wait
                indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should require no
                arguments.
            :returns: `True` if the command was successful.
        """
        cmd = "SecureUpdateAll" if secure else "LegacyAll"
        return self._runSimpleCommand({'EBMLCommand': {cmd: {}}},
                                      statusCode=DeviceStatusCode.RESET_PENDING,
                                      timeoutMsg="Timed out waiting for update to begin",
                                      wait=wait,
                                      timeout=timeout,
                                      callback=callback)


    def scanWifi(self,
                 timeout: Union[int, float] = 10,
                 interval: float = .25,
                 callback: Optional[Callable] = None) -> Union[None, list]:
        """ Initiate a scan for Wi-Fi access points (APs). Applicable only
            to devices with Wi-Fi hardware.

            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception. `None` or -1 will wait
                indefinitely.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will
                be cancelled. The callback function should require no
                arguments.
            :return: A list of dictionaries, one for each access point,
                with keys:
                - ``SSID`` (str): The access point name.
                - ``RSSI`` (int): The AP's signal strength.
                - ``AuthType`` (int): The authentication (security) type.
                    Currently, this is either 0 (no authentication) or 1
                    (any authentication).
                - ``Known`` (bool): Is this access point known (i.e. has
                    a stored password on the device)?
                - ``Selected`` (bool): Is this the currently selected AP?

            :raise DeviceTimeout: Raised if 'timeout' seconds have gone by
                without getting a response
        """
        # TODO: Remove this workaround. It exists because too many Wi-Fi AP
        #  produce too much data for current FW to transmit via serial.
        try:
            return super().scanWifi(timeout, interval, callback)
        except CRCError:
            logger.debug('CRCError in SerialCommandInterface.scanWifi(), '
                         'too many APs? Falling back to FileCommandInterface.')

        if not hasattr(self, '_fileinterface'):
            if FileCommandInterface.hasInterface(self.device):
                self._fileinterface = FileCommandInterface(self.device)
            else:
                raise IOError('SerialCommandInterface.scanWifi() failed, and '
                              'device does not support alternative '
                              'FileCommandInterface')

        return self._fileinterface.scanWifi(timeout, interval, callback)


# ===========================================================================
#
# ===========================================================================

class FileCommandInterface(CommandInterface):
    """
    A mechanism for sending commands to a recorder via the `COMMAND` file.
    """

    def _writeCommand(self,
                      packet: Union[AnyStr, ByteString]) -> int:
        """
        Send an encoded EBMLCommand element. This is a low-level write; the
        data should include any transport-specific packaging. It generally
        should not be used directly.

        :param packet: An encoded EBMLCommand element.
        :return: The number of bytes written.
        """
        with self.device._busy:
            with open(self.device.commandFile, 'wb') as f:
                f.write(packet)

        return len(packet)


    @classmethod
    def hasInterface(cls, device) -> bool:
        """ Determine if a device supports this `CommandInterface` type.

            :param device: The recorder to check.
            :return: `True` if the device supports the interface.
        """
        if device.isVirtual or not device.path:
            return False

        # Old SlamStick devices may not support COMMAND. They should get
        # the `LegacyFileCommandInterface` because it is checked first,
        # but check anyway, just to make sure.
        if (not device.getInfo('McuType', '').startswith(('EFM32GG11', 'STM32'))
                and device.firmwareVersion <= 19):
            return False

        # Newer firmware will explicitly indicate in DEVINFO if the device
        # supports the COMMAND file interface. All EFM32 devices should
        # support it, but their FW may not report it in DEVINFO, so assume
        # the absence of the `FileCommandInterface` element means 'yes'.
        return bool(device.getInfo('FileCommandInterface', 1))


    @property
    def available(self) -> bool:
        """ Is the command interface available and able to accept commands? """
        return (self.device.available
                and os.path.isfile(self.device.commandFile))


    def _readResponse(self,
                      timeout: Optional[Union[int, float]] = None,
                      callback: Optional[Callable] = None) -> Union[dict, None]:
        """
        Helper to retrieve an EBML response from the device's `RESPONSE` file.

        :param timeout: Time to wait for a valid response. Not applicable to
            `FileCommandInterface` (timeout handled by caller).
        :param callback: A function to call each response-checking
            cycle. If the callback returns `True`, the wait for a response
            will be cancelled. The callback function should require no
            arguments.
        :return: A `dict` of response data, or `None` if `callback` caused
            the process to cancel.
        """
        with self.device._busy:
            responseFile = os.path.join(self.device.path, self.device._RESPONSE_FILE)
            if not os.path.isfile(responseFile):
                return None

            try:
                raw = os_specific.readUncachedFile(responseFile)
                data = self._decode(raw)

                if 'EBMLResponse' not in data:
                    logger.warning('Response did not contain an EBMLResponse element')

                return data.get('EBMLResponse', data)

            except (AttributeError, IndexError, KeyError, TypeError) as err:
                # TODO: Better exception handling in readResponse()
                warnings.warn("Ignoring exception in {}._readResponse(): {!r}"
                              .format(type(self).__name__, err))

        return None


    def _getTime(self,
                 pause=False) -> Tuple[Epoch, Epoch]:
        """
        Called by `Recorder.getTime()` and `Recorder.getClockDrift()`.

        Read the date/time from the device.

        :param pause: If `True` (default), the system waits until a
            whole-numbered second before reading the device's clock. This
            may improve accuracy since the device's realtime clock is in
            integer seconds.
        :return: The system time and the device time. Both are epoch
            (UNIX) time (seconds since 1970-01-01T00:00:00).
        """
        with self.device._busy:
            if pause:
                t = int(time())
                while int(time()) == t:
                    pass
            sysTime, devTime = os_specific.readRecorderClock(self.device.clockFile)
            devTime = self.device._TIME_PARSER.unpack_from(devTime)[0]

        return sysTime, devTime


    def _setTime(self,
                 t: Optional[int] = None,
                 pause: bool = True) -> Tuple[Epoch, Epoch]:
        """
        Called by `Recorder.setTime()`.

        Set a recorder's date/time. A variety of standard time types are
        accepted. Note that the minimum unit of time is the whole second.

        :param t: The time to write, as seconds since the epoch. The
            current time  (from the host) is used if `None` (default).
        :param pause: If `True` (default), the system waits until a
            whole-numbered second before setting the clock. This may
            improve accuracy across multiple recorders, but may take up
            to a second to run. Not applicable if a specific time is
            provided (i.e. `t` is not `None`).
        :return: The system time (float) and time that was set (integer).
            Both are UNIX epoch time (seconds since 1970-01-01T00:00:00).
        """
        if t is None:
            t = time()
            if pause:
                t += 1
        else:
            pause = False

        t = int(t)
        payload = self.device._TIME_PARSER.pack(t)

        t0 = time()
        with open(self.device.clockFile, 'wb') as f:
            if pause:
                while t0 < t:
                    t0 = time()
            f.write(payload)

        return t0, t


    def _sendCommand(self,
                     cmd: dict,
                     response: bool = True,
                     timeout: Union[int, float] = 10,
                     interval: float = .25,
                     index: bool = True,
                     callback: Optional[Callable] = None) -> Union[None, dict]:
        """ Send a raw command to the device and (optionally) retrieve the
            response.

            :param cmd: The raw EBML representing the command.
            :param response: If `True`, wait for and return a response.
            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception. `None` or -1 will wait
                indefinitely.
            :param interval: Time (in seconds) between checks for a
                response.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should require no
                arguments.

            :raise: DeviceTimeout
        """
        if 'EBMLCommand' in cmd and index:
            self.index += 1
            cmd['EBMLCommand']['CommandIdx'] = self.index

        ebml = self._encode(cmd)

        now = time()
        timeout = -1 if timeout is None else timeout
        deadline = now + timeout

        with self.device._busy:
            self.lastCommand = (now, deepcopy(cmd))

            # Wait until the command queue is empty.
            # The file interface does this first.
            while True:  # a `while True` infinite loop
                data = self._readResponse()
                if data:
                    idx = data.get('ResponseIdx')
                    queueDepth = data.get('CMDQueueDepth', 1)
                    if queueDepth > 0:
                        break
                else:
                    sleep(interval)

                if timeout >= 0 and time() > deadline:
                    if not response:
                        logger.debug('Ignoring timeout waiting for CMDQueue '
                                     'to empty because no response required')
                        return

                    raise DeviceTimeout("Timed out waiting for device to complete "
                                        "queued commands (%s remaining)" % queueDepth)

                if callback is not None and callback():
                    return

            self._writeCommand(ebml)

            while timeout < 0 or time() <= deadline:
                data = self._readResponse()

                if data and data.get("ResponseIdx") != idx:
                    return data

                if callback is not None and callback():
                    return

                sleep(interval)

            if not response:
                logger.debug('Ignoring timeout waiting for response '
                             'because no response required')
                return

            raise DeviceTimeout("Timed out waiting for command response (%s seconds)" % timeout)


    # =======================================================================
    # Firmware/Userpage/Bootloader updating
    # =======================================================================

    def _runSimpleCommand(self,
                          cmd: dict,
                          statusCode: int = DeviceStatusCode.RESET_PENDING,
                          timeoutMsg: Optional[str] = None,
                          wait: bool = True,
                          timeout: Union[int, float] = 5,
                          callback: Optional[Callable] = None) -> bool:
        """ Send a command that will cause the device to reset/dismount. No
            response is expected/required.

            :param cmd: The command to execute. It is assumed to be a
                legacy command, with no outer `<EBMLCommand>` wrapper.
                Only the first 2 bytes will be sent.
            :param statusCode: The ``<DeviceStatusCode>`` expected in the
                acknowledgement (if the interface supports one).
            :param wait: If `True`, wait for the recorer to respond and/or
                dismount.
            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception. 0 will return
                immediately; `None` or -1 will wait indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :returns: `True` if the command was successful.
        """
        msg = self._encode(cmd)[:2]
        self._writeCommand(msg)

        return self.awaitReboot(timeout=timeout if wait else 0,
                                timeoutMsg=timeoutMsg,
                                callback=callback)


    def _updateAll(self,
                   secure: bool = True,
                   wait: bool = True,
                   timeout: Union[int, float] = 10,
                   callback: Optional[Callable] = None) -> bool:
        """ Send the `"SecureUpdateAll"` command (or `"LegacyAll"` if the
            firmware is a simple binary rather than a signed package).

            :param secure: If `True`, use the `"SecureUpdateAll"` command
                instead of `"LegacyAll"`.
            :param wait: If `True`, wait for the recorer to dismount,
                indicating the command has executed.
            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception. 0 will return
                immediately; `None` or -1 will wait indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :return:
        """
        cmd = "SecureUpdateAll" if secure else "LegacyAll"
        return self._runSimpleCommand({cmd: {}},
                                      timeoutMsg="Timed out waiting for update to begin",
                                      wait=wait,
                                      timeout=timeout,
                                      callback=callback)


    def startRecording(self,
                       wait: bool = True,
                       timeout: Union[int, float] = 10,
                       callback: Optional[Callable] = None) -> bool:
        """ Start the device recording, if supported.

            :param wait: If `True`, wait for the recorer to dismount,
                indicating the recording has started.
            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception. 0 will return
                immediately; `None` or -1 will wait indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :returns: `True` if the command was successful.
        """
        if not self.canRecord:
            return False

        # FUTURE: Write commands wrapped in a <EBMLCommand> element?
        #  Exclude LegacyFileCommandInterface.
        return self._runSimpleCommand({'RecStart': {}},
                                      timeoutMsg="Timed out waiting for recording to start",
                                      wait=wait,
                                      timeout=timeout,
                                      callback=callback)


    def reset(self,
              wait: bool = True,
              timeout: Union[int, float] = 10,
              callback: Optional[Callable] = None) -> bool:
        """ Reset (reboot) the recorder.

            :param wait: If `True`, wait for the recorer to dismount,
                indicating the reset has taken effect.
            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception. 0 will return
                immediately; `None` or -1 will wait indefinitely.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :returns: `True` if the command was successful.
        """
        # FUTURE: Write commands wrapped in a <EBMLCommand> element?
        #  Exclude LegacyFileCommandInterface.
        return self._runSimpleCommand({'Reset': {}},
                                      timeoutMsg="Timed out waiting for device to reset",
                                      wait=wait,
                                      timeout=timeout,
                                      callback=callback)


# ===========================================================================
#
# ===========================================================================

class LegacyFileCommandInterface(FileCommandInterface):
    """
    A mechanism for sending commands to a recorder via the `COMMAND` file.
    For devices using old firmware that supports only a subset of
    commands.
    """

    @classmethod
    def hasInterface(cls, device) -> bool:
        """ Determine if a device supports this `CommandInterface` type.

            :param device: The recorder to check.
            :return: `True` if the device supports the interface.
        """
        if device.getInfo('McuType', "EFM32GG330") != "EFM32GG330":
            return False

        return 17 <= device.firmwareVersion <= 19


    @property
    def canCopyFirmware(self) -> bool:
        """ Can the device get new firmware/userpage from a file? """
        return False


    @property
    def canRecord(self) -> bool:
        """ Can the device record on command? """
        return not (self.device.isVirtual or self.device.path is None)


    def setKeys(self, *args, **kwargs):
        """ Update the device's key bundle. Not supported on this device.
        """
        raise UnsupportedFeature(self, self.setKeys)


    def updateDevice(self, *args, **kwargs) -> bool:
        """ Apply a firmware package and/or device description data update.
            Not supported on this device; serial bootloader connection
            required.
        """
        raise UnsupportedFeature(self, self.updateDevice)


# ===========================================================================
#
# ===========================================================================

#: A list of all `CommandInterface` types, used when finding a device's
#   interface. `FileCommandInterface` should go last, since devices with
#   "better" interfaces may support it as a fallback. New interface types
#   defined elsewhere should append/insert themselves into this list.
INTERFACES = [SerialCommandInterface,
              LegacyFileCommandInterface,
              FileCommandInterface]
