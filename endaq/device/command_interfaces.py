"""
Proof-of-concept implementation of basic serial command interface.
"""

import calendar
from datetime import datetime
import errno
import os.path
import shutil
import sys
from time import sleep, time, struct_time
from typing import Optional, Tuple, Union, Callable
import warnings

import logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

from ebmlite import loadSchema
import serial
import serial.tools.list_ports

from .exceptions import DeviceError, CommandError, ConfigError, DeviceTimeout, UnsupportedFeature
from .hdlc import hdlc_decode, hdlc_encode, HDLC_BREAK_CHAR
from .types import Epoch

if sys.platform == 'darwin':
    from . import macos as os_specific
elif 'win' in sys.platform:
    from . import win as os_specific
elif sys.platform == 'linux':
    from . import linux as os_specific


# ===========================================================================
#
# ===========================================================================


class CommandInterface:
    """
    Base class for command interfaces, the mechanism that sends the command
    to the device.

    :ivar timeout: The default response timeout.
    :ivar status: The last reported device status. Not available on all
        interface types. A tuple containing the status code and a
        status message string (optional).
    """

    # DeviceStatusCode responses. Note: not reported over all interfaces.
    # "Okay" status codes:
    STATUS_IDLE = 0
    STATUS_RECORDING = 10
    STATUS_RESET_PENDING = 20
    STATUS_START_PENDING = 30

    # Error status codes:
    ERR_BUSY = -10
    ERR_INVALID_COMMAND = -20
    ERR_UNKNOWN_COMMANND = -30
    ERR_BAD_PAYLOAD = -40
    ERR_BAD_EBML = -50
    ERR_BAD_CHECKSUM = -60
    ERR_BAD_PACKET = -70

    # For mapping status code numbers back to names. Populated later.
    STATUS_CODES = {}

    # Wi-Fi-related response codes.
    # Values for `<CurrentWiFiStatus>` in `<NetworkStatusResponse>`
    WIFI_STATUS_IDLE = 0
    WIFI_STATUS_PENDING = 1
    WIFI_STATUS_CONNECTED = 2

    # Values for `<WiFiConnectionStatus>` in `<QueryWiFiResponse>`
    WIFI_CONNECTION_FAILED = 0
    WIFI_CONNECTING = 1
    WIFI_CONNECTED = 2
    WIFI_CONNECTED_CLOUD = 3

    # Default maximum encoded command length (bytes). Only applicable to
    # certain interfaces.
    DEFAULT_MAX_COMMAND_SIZE = None


    def __init__(self,
                 device,
                 timeout: Union[int, float] = 1):
        """
        Constructor.

        :param device: The Recorder to which to interface.
        :param timeout: Default time to wait (in seconds) for commands
            to process.
        """
        self.schema = loadSchema('command-response.xml')

        self.device = device
        self.timeout = timeout
        self.index = 0

        # Last reported device status. Not available on all interfaces.
        self.status = None, None

        # Some interfaces (i.e. serial) have a maximum packet size.
        self.maxCommandSize = self.DEFAULT_MAX_COMMAND_SIZE


    @classmethod
    def hasInterface(cls, device) -> bool:
        """
        Determine if a device supports this `CommandInterface` type.

        :param device:
        :return:
        """
        raise NotImplementedError


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
        connection. Fails silently.

        :return: `True` if the connection was reset (or the interface type
            has no persistent connection).
        """
        return True


    def encode(self, data: dict) -> Union[bytearray, bytes]:
        """
        Prepare a packet of command data for transmission, doing any
        preparation required by the interface's medium.

        :param data: The unencoded command `dict`.
        :return: The encoded command data, with any class-specific
            wrapping or other preparations.
        """
        ebml = self.schema.encodes(data, headers=False)

        if self.maxCommandSize is not None and len(ebml) > self.maxCommandSize:
            raise CommandError("Command too large ({}); max size is {}".format(
                    len(ebml), self.maxCommandSize))

        return ebml


    def decode(self, packet: Union[bytearray, bytes]) -> dict:
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

    def writeCommand(self, packet: Union[bytearray, bytes]) -> int:
        """
        Send an encoded EBMLCommand element. This is a low-level write; the
        data should include any transport-specific packaging. It generally
        should not be used directly.

        Must be implemented in every subclass.

        :param packet: An encoded EBMLCommand element.
        :return: The number of bytes written.
        """
        raise NotImplementedError


    def readResponse(self,
                     timeout: Optional[Union[int, float]] = None,
                     callback: Optional[Callable] = None) -> Union[None, dict]:
        """
        Wait for and retrieve the response to a serial command. Does not do any
        processing other than (attempting to) decode the EBML payload.

        Must be implemented in every subclass.

        :param timeout: Time to wait for a valid response.
        :param callback: A function to call each response-checking
            cycle. If the callback returns `True`, the wait for a response
            will be cancelled. The callback function should take no
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
            Both are *NIX epoch time (seconds since 1970-01-01T00:00:00).
        """
        raise NotImplementedError


    def getTime(self,
                epoch: bool = True) -> Union[Tuple[datetime, datetime], Tuple[Epoch, Epoch]]:
        """ Read the date/time from the device.

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
                retries: int = 1) -> Epoch:
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
                fail. Random filesystem things can potentially cause hiccups.
        :return: The system time (float) and time that was set (integer).
            Both are *NIX epoch time (seconds since 1970-01-01T00:00:00).
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


    def sendCommand(self,
                    cmd: dict,
                    response: bool = True,
                    timeout: float = 10,
                    interval: float = .25,
                    index: bool = True,
                    callback: Optional[Callable] = None) -> Union[None, dict]:
        """ Send a raw command to the device and (optionally) retrieve the
            response.
            Must be implemented in every subclass.

            :param cmd: The raw EBML representing the command.
            :param response: If `True`, wait for and return a response.
            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a
                response.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.

            @raise DeviceTimeout
        """
        raise NotImplementedError


    def _runSimpleCommand(self,
                          cmd: dict,
                          statusCode: int = STATUS_RESET_PENDING,
                          timeoutMsg: Optional[str] = None,
                          wait: bool = True,
                          timeout: float = 5,
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
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :returns: `True` if the command was successful.
        """
        self.sendCommand(cmd, response=False, timeout=timeout, callback=callback)

        # Since no response is expected, a failure to read a response caused
        # by the device resetting will just set self.status to (None, None).
        # Success is self.status[0] == None or the expected status code.
        if self.status[0] is not None and self.status[0] != statusCode:
            return False

        return self.awaitReboot(timeout=timeout if wait else 0,
                                timeoutMsg=timeoutMsg,
                                callback=callback)


    def startRecording(self,
                       timeout: float = 5,
                       callback: Optional[Callable] = None) -> bool:
        """ Start the device recording, if supported.
            Must be implemented in every subclass.

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :returns: `True` if the command was successful.
        """
        raise NotImplementedError


    def reset(self,
              timeout: float = 5,
              callback: Optional[Callable] = None) -> bool:
        """ Reset (reboot) the recorder.
            Must be implemented in every subclass.

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :returns: `True` if the command was successful.
        """
        raise NotImplementedError


    def getBatteryStatus(self,
                         timeout: float = 1,
                         callback: Optional[Callable] = None) -> bool:
        """ Get the status of the recorder's battery. Not supported on all
            devices.

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :return:
        """
        # Only interfaces that support this method will implement it.
        raise UnsupportedFeature(self, self.getBatteryStatus)


    def ping(self,
             data: Optional[Union[bytearray, bytes]] = None,
             timeout: float = 5,
             callback: Optional[Callable] = None) -> bytes:
        """ Verify the recorder is present and responding. Not supported on
            all devices.

            :param data: An optional binary payload, returned by the recorder
                verbatim.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :return: The received data, which should be identical to the
                data sent.
        """
        # Only interfaces that support this method will implement it.
        raise UnsupportedFeature(self, self.ping)


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
                respond. 0 will return immediately.
            :param timeoutMsg: A command-specific message to use when raising
                a `DeviceTimeout` exception.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :return: `True` if the device unmounted. `False` if it is a
                virtual device, or the wait was cancelled by the callback.
        """
        if not timeout:
            return True

        with self.device._busy:
            deadline = time() + timeout
            while time() < deadline:
                if callback and callback():
                    return False
                # Two checks, since former is a property that sets latter
                # and path itself isn't a reliable test in Linux
                if not (os.path.exists(self.device.path)
                        and os.path.isfile(self.device.infoFile)):
                    return True
                sleep(0.1)

            timeoutMsg = timeoutMsg or "Timed out waiting for device to dismount"
            raise DeviceTimeout(timeoutMsg)


    def _updateAll(self,
                   secure: True,
                   wait: bool = True,
                   timeout: float = 10,
                   callback: Optional[Callable] = None) -> bool:
        """ Send interface-specific update command. Implemented for each
            subclass.

            :param wait: If `True`, wait for the recorer to dismount,
                indicating the update has started.
            :param timeout: Time (in seconds) to wait for the recorder to
                dismount, implying the updates are being applied. 0 will
                return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
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
                     timeout: float = 10,
                     callback: Optional[Callable] = None) -> bool:
        """ Apply a firmware package and/or device description data to the
            device. If no filenames are supplied, it will be assumed that one
            or both of the update files have been manually copied to the
            recorder; a `FileNotFound` exception will be raised if neither
            exist on the device.

            :param firmware: The name of the firmware file (typically
                `".pkg"`, or `".bin"` on older devices). If provided, any
                existing firmware update files already on the device will be
                overwritten.
            :param userpage: The name of the "userpage" device description
                file (typically `".bin"`). If provided, any existing
                userpage update files already on the device will be
                overwritten. Warning: userpage data is specific to an
                individual recorder. Do not install a userpage file created
                for a different device.
            :param clean: If `True`, any existing firmware or userpage
                update files will be removed from the device. Used if either
                `firmware` or `userpage` is supplied (but not both).
            :param timeout: Time (in seconds) to wait for the recorder to
                dismount, implying the updates are being applied. 0 will
                return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :returns: `True` if the device rebooted. This does not indicate
                that the updates were successfully applied.
        """
        with self.device._busy:
            # Update filenames on device
            fw = os.path.join(self.device.path, self.device._FW_UPDATE_FILE)
            up = os.path.join(self.device.path, self.device._USERPAGE_UPDATE_FILE)
            sig = fw + ".sig"

            if firmware is not None:
                ext = os.path.splitext(firmware)[-1].lower()
                if ext not in ('.pkg', '.bin'):
                    raise TypeError("Firmware update file must be type .pkg or .bin")

                # Special case: non-PKG firmware
                # FUTURE: Handle in Recorder subclass instead?
                if ext == '.bin':
                    fw = os.path.join(os.path.dirname(fw), 'firmware.bin')

            hasFw = self._copyUpdateFile(firmware, fw, clean)
            hasUp = self._copyUpdateFile(userpage, up, clean)

            isPkg = hasFw and fw.lower().endswith('pkg')
            signature = None if firmware is None or not isPkg else firmware + ".sig"

            if isPkg and not self._copyUpdateFile(signature, sig, clean):
                raise FileNotFoundError(errno.ENOENT,
                                        "Firmware signature file not found",
                                        (signature or sig))

            if not hasFw and not hasUp:
                raise FileNotFoundError(errno.ENOENT,
                                        "Device has no update files",
                                        os.path.dirname(fw))

            return self._updateAll(secure=isPkg, timeout=timeout, callback=callback)


    def setKeys(self, keys: Union[bytearray, bytes],
                timeout: float = 5,
                callback: Optional[Callable] = None):
        """ Update the device's key bundle

            :param keys: The key data.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :return:
        """
        cmd = {'EBMLCommand': {'SetKeys': keys}}
        response = self.sendCommand(cmd, timeout=timeout, callback=callback)


    # =======================================================================
    # Wi-Fi
    # =======================================================================

    def setAP(self, ssid: str, password: Optional[str] = None):
        """ Quickly set the Wi-Fi access point (router) and password.
            Applicable only to devices with Wi-Fi hardware.

            :param ssid: The SSID (name) of the wireless access point.
            :param password: The access point password.
        """
        cmd = {'SSID': ssid, 'Selected': 1}
        if password is not None:
            cmd['Password'] = password
        return self.setWifi(cmd)


    def setWifi(self,
                wifi_data: dict,
                timeout: int = 10,
                interval: float = 1.25,
                callback: Optional[Callable] = None):
        """ Configure all known Wi-Fi access points. Applicable only
            to devices with Wi-Fi hardware.

            :param wifi_data: The information about the Wi-Fi networks to be
                set on the device.  Specifically, it's a list of dictionaries,
                where each element in the list corresponds to one of the Wi-Fi
                networks to be set.  The following are two examples of this:
                [{'SSID': 'office_wifi', 'Selected': 1, 'Password': 'pass123'}]
                or
                [{'SSID': 'ssid_1', 'Selected': 1, 'Password': 'pass_1'},
                 {'SSID': 'ssid_2', 'Selected': 0},
                 {'SSID': 'ssid_1', 'Selected': 0, 'Password': 'pass_3'}]
            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will be
                cancelled. The callback function should take no arguments.

            :raise DeviceTimeout: Raised if 'timeout' seconds have gone by
                without getting a response
        """
        # FUTURE: Ensure that the setting of multiple networks at once behaves
        #  as expected (not currently implemented in FW?)

        if not self.device.hasWifi:
            raise UnsupportedFeature('{!r} has no Wi-Fi adapter'.format(self.device))

        cmd = {'EBMLCommand': {'SetWiFi': {"AP": wifi_data}}}

        self.sendCommand(cmd,
                         response=False,
                         timeout=timeout,
                         interval=interval,
                         callback=callback)


    def queryWifi(self,
                  timeout: int = 10,
                  interval: float = .25,
                  callback: Optional[Callable] = None) -> Union[None, dict]:
        """ Check the current state of the Wi-Fi (if present). Applicable only
            to devices with Wi-Fi hardware.

            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will be
                cancelled. The callback function should take no arguments.
            :return: None if no information was recieved, else it will return
                the information from the ``QueryWiFiResponse`` command (this
                return statement is not used anywhere)

            :raise DeviceTimeout: Raised if 'timeout' seconds have gone by
                without getting a response
        """
        if not self.device.hasWifi:
            raise UnsupportedFeature('{!r} has no Wi-Fi adapter'.format(self.device))

        response = self.sendCommand(
            {'EBMLCommand': {'QueryWiFi': {}}},
            response=True,
            timeout=timeout,
            interval=interval,
            callback=callback)

        if response is None:
            return None

        return response.get('QueryWiFiResponse')


    def scanWifi(self, timeout: int = 10,
                 interval: float = .25,
                 callback: Optional[Callable] = None) -> Union[None, list]:
        """ Initiate a scan for Wi-Fi access points (APs). Applicable only
            to devices with Wi-Fi hardware.

            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will
                be cancelled. The callback function should take no arguments.

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
        if not self.device.hasWifi:
            raise UnsupportedFeature('{!r} has no Wi-Fi adapter'.format(self.device))

        cmd = {'EBMLCommand': {'WiFiScan': None}}

        response = self.sendCommand(cmd, True, timeout, interval, callback)

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
                    destination: Optional[str] = None,
                    timeout: float = 10,
                    callback: Optional[Callable] = None):
        """ Update the ESP32 firmware. Applicable only to devices with
            ESP32 Wi-Fi hardware.

            :param firmware: The name of the ESP32 firmware package (.bin).
            :param destination: The name of the firmware package after being
                copied to the device, an alternative to the default.
                Optional; typically left `None`.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :return:
        """
        # FUTURE: This (and other file-based update) will need refactoring
        #  if/when we have another means of uploading (serial, wireless,
        #  etc.)
        if not self.device.hasWifi or "ESP" not in self.device.hasWifi:
            raise UnsupportedFeature("{!r} does not have an ESP32".format(self.device))

        firmware = os.path.abspath(firmware)

        if not destination:
            destination = os.path.abspath(os.path.join(self.device.path,
                                                       self.device._ESP_UPDATE_FILE))
            payload = {}
        else:
            payload = {'PackagePath': destination}

        self._copyUpdateFile(firmware, destination)

        cmd = {'EBMLCommand': {'ESPFW': payload}}
        response = self.sendCommand(cmd, timeout=timeout, callback=callback)


# Populate the STATUS_CODES dictionary, mapping code numbers back to names
CommandInterface.STATUS_CODES = {v: k for k, v in CommandInterface.__dict__.items()
                                 if k.startswith("ERR_") or k.startswith("STATUS_")
                                 and k != "STATUS_CODES"}


# ===========================================================================
#
# ===========================================================================

class SerialCommandInterface(CommandInterface):
    """
    A mechanism for sending commands to a recorder via a serial port.

    :ivar timeout: The default response timeout.
    :ivar status: The last reported device status. Not available on all
        interface types.
    :ivar make_crc: If `True`, generate CRCs for outgoing packets.
    :ivar ignore_crc: If `True`, ignore the CRC on response packets.
    """

    # USB serial port vendor and product IDs, for finding the right device
    VID, PID = 0x10C4, 0x0004  # SiLabs USB Serial, e.g. enDAQ recorders

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
                 device,
                 timeout: Union[int, float] = 1,
                 make_crc: bool = True,
                 ignore_crc: bool = False,
                 **serial_kwargs):
        """
        Constructor.

        :param device: The Recorder to which to interface.
        :param timeout: The default response timeout.
        :param make_crc: If `True`, generate CRCs for outgoing packets.
        :param ignore_crc: If `True`, ignore the CRC on response packets.

        If additional keyword arguments are provided, they will be used
        when opening the serial port.
        """
        super().__init__(device, timeout=timeout)

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
    def hasInterface(cls, device) -> bool:
        """ Determine if a device supports this `CommandInterface` type.

            :param device: The recorder to check.
            :return: `True` if the device supports the interface.
        """
        if device.isVirtual:
            return False

        return bool(cls.findSerialPort(device))


    @classmethod
    def findSerialPort(cls, device) -> Union[None, str]:
        """ Find the path/name/number of a serial port corresponding to a
            given serial number.

            :param device: The recorder to check.
            :return: The corresponding serial port path/name/number, or
                `None` if no matching port is found.
        """
        if device.isVirtual:
            return None

        for p in serial.tools.list_ports.comports():
            if not (p.vid == cls.VID and p.pid == cls.PID):
                continue
            try:
                sn = int(p.serial_number)
                if sn == device.serialInt:
                    return p.device
            except ValueError as err:
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
                    if self.port.closed:
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
            raise DeviceError('No serial port found for {}'.format(self.device))

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
            if self.port and not self.port.closed:
                self.port.close()
                return self.port.closed
        except (IOError, OSError, serial.SerialException) as err:
            # Disconnected device can cause this.
            logger.debug("Ignoring exception when closing {} (probably okay): "
                         "{!r}".format(type(self).__name__, err))
        return True


    def encode(self, data: dict) -> bytearray:
        """
            Generate a serial packet containing EBMLCommand data. Separated from
            sending for use with time-critical functions to minimize latency.

            :param data: The unencoded command `dict`.
            :return: A `bytearray` containing the packetized EBMLCommand data.
        """
        ebml = super().encode(data)

        # Header: address 0 (broadcast), EBML data, immediate write.
        packet = bytearray([0x80, 0x26, 0x00, 0x0A])
        packet.extend(ebml)
        packet = hdlc_encode(packet, crc=self.make_crc)
        return packet


    def decode(self,
               packet: Union[bytearray, bytes]) -> dict:
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
        # HDLC escaped, short header, payload, crc16
        packet = hdlc_decode(packet, ignore_crc=self.ignore_crc)
        if packet.startswith(b'\x81\x00'):
            resultcode = packet[2]
            if resultcode == 0:
                return super().decode(packet[3:-2])
            else:
                errname = {0x01: "Corbus command failed",
                           0x07: "bad Corbus command"}.get(resultcode, "unknown error")
                raise CommandError("Response header indicated an error (0x{:02x}: {})".format(resultcode, errname))
        else:
            raise CommandError('Response was corrupted or incomplete; did not have expected Corbus header')


    def writeCommand(self,
                     packet: Union[bytearray, bytes]) -> int:
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


    def readResponse(self,
                     timeout: Optional[float] = None,
                     callback: Optional[Callable] = None) -> Union[None, dict]:
        """
        Wait for and retrieve the response to a serial command. Does not do any
        processing other than (attempting to) decode the EBML payload.

        :param timeout: Time to wait for a valid response.
        :param callback: A function to call each response-checking
            cycle. If the callback returns `True`, the wait for a response
            will be cancelled. The callback function should take no
            arguments.
        :return: A `dict` of response data, or `None` if `callback` caused
            the process to cancel.
        """
        timeout = self.timeout if timeout is None else timeout
        deadline = time() + timeout

        buf = b''

        while time() < deadline:
            if callback is not None and callback() is True:
                return
            if self.port.in_waiting:
                buf += self.port.read()
                self._lastbuf = buf
                if HDLC_BREAK_CHAR in buf:
                    packet, _, buf = buf.partition(HDLC_BREAK_CHAR)
                    if packet.startswith(b'\x81\x00'):
                        response = self.decode(packet)
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


    def sendCommand(self,
                    cmd: dict,
                    response: bool = True,
                    timeout: float = 10,
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
                raising a `DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a
                response.
            :param index: If `True` (default), include an incrementing
                'command index' (for matching responses to commands).
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :return: The response dictionary, or `None` if `response` is
                `False`.

            @raise DeviceTimeout
        """
        now = time()
        deadline = now + timeout

        with self.device._busy:
            while True:
                if 'EBMLCommand' in cmd and index:
                    self.index += 1
                    cmd['EBMLCommand']['CommandIdx'] = self.index

                packet = self.encode(cmd)
                self.writeCommand(packet)

                try:
                    resp = self.readResponse(timeout, callback=callback)
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
                    self.status = resp.get('DeviceStatusCode', 0), resp.get('DeviceStatusMessage')
                    queueDepth = resp.get('CMDQueueDepth', 1)

                    if self.status[0] < 0:
                        raise DeviceError(*self.status)

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
                if time() >= deadline:
                    if queueDepth == 0:
                        raise DeviceTimeout('Timed out waiting for opening in command queue')
                    else:
                        raise DeviceTimeout('Timed out waiting for command response')


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

            response = self.sendCommand(command)
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
            Both are *NIX epoch time (seconds since 1970-01-01T00:00:00).
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

        self.sendCommand({'EBMLCommand': {'SetClock': payload}})

        return t0, t


    def ping(self,
             data: Optional[Union[bytearray, bytes]] = None,
             timeout: float = 10,
             interval: float = .25,
             callback: Optional[Callable] = None) -> dict:
        """ Verify the recorder is present and responding. Not supported on
            all devices.

            :param data: Optional data, which will be returned verbatim.
            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a
                response.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :return: The received data, which should be identical to the
                data sent.
        """
        cmd = {'EBMLCommand': {'SendPing': b'' if data is None else data}}
        response = self.sendCommand(cmd, timeout=timeout, interval=interval,
                                    callback=callback)

        if 'PingReply' not in response:
            raise CommandError('Ping response did not contain a PingReply')

        return response['PingReply']


    def getBatteryStatus(self,
                         timeout: float = 1,
                         callback: Optional[Callable] = None) -> dict:
        """ Get the status of the recorder's battery. Not supported on all
            devices.

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :return: A dictionary with the parsed battery status. It will
                always contain the key `"hasBattery"`, and if that is `True`,
                it will contain other keys:

                - `"charging"`: (bool)
                - `"percentage"`: (bool) `True` if the reported charge
                    level is a percentage, or 3 states (0 = empty,
                    255 = full, anything else is 'some' charge).
                - `"level"`: (int) The current battery charge level.

                If the device is capable of reporting if it is receiving
                external power, the dict will contain `"externalPower"`
                (bool).
        """
        cmd = {'EBMLCommand': {'GetBattery': {}}}
        response = self.sendCommand(cmd, timeout=timeout,
                                    callback=callback).get('BatteryState')

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
                       timeout: float = 5,
                       callback: Optional[Callable] = None) -> bool:
        """ Start the device recording.

            :param wait: If `True`, wait for the recorer to respond and/or
                dismount, indicating the recording has started.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :returns: `True` if the command was successful.
        """
        return self._runSimpleCommand({'EBMLCommand': {'RecStart': {}}},
                                      statusCode=self.STATUS_START_PENDING,
                                      timeoutMsg="Timed out waiting for recording to start",
                                      wait=wait,
                                      timeout=timeout,
                                      callback=callback)


    def reset(self,
              wait: bool = True,
              timeout: float = 5,
              callback: Optional[Callable] = None) -> bool:
        """ Reset (reboot) the recorder.

            :param wait: If `True`, wait for the recorer to respond and/or
                dismount, indicating the reset has started.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :returns: `True` if the command was successful.
        """
        return self._runSimpleCommand({'EBMLCommand': {'Reset': {}}},
                                      statusCode=self.STATUS_RESET_PENDING,
                                      timeoutMsg="Timed out waiting for device to reset",
                                      wait=wait,
                                      timeout=timeout,
                                      callback=callback)


    def _updateAll(self,
                   secure: bool = True,
                   wait: bool = True,
                   timeout: float = 5,
                   callback: Optional[Callable] = None):
        """ Send the 'secure update all' command, installing any userpage
            and/or firmware update files copied to the device.

            :param wait: If `True`, wait for the recorer to dismount,
                indicating the update has started.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :returns: `True` if the command was successful.
        """
        cmd = "SecureUpdateAll" if secure else "LegacyAll"
        return self._runSimpleCommand({'EBMLCommand': {cmd: {}}},
                                      statusCode=self.STATUS_RESET_PENDING,
                                      timeoutMsg="Timed out waiting for update to begin",
                                      wait=wait,
                                      timeout=timeout,
                                      callback=callback)


# ===========================================================================
#
# ===========================================================================

class FileCommandInterface(CommandInterface):
    """
    A mechanism for sending commands to a recorder via the `COMMAND` file.
    """

    def writeCommand(self,
                     packet: Union[bytearray, bytes]) -> int:
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

        # Old SlamStick devices may not support COMMAND. Use `canRecord`,
        # which checks the firmware version. Hack.
        if 'SlamStick' in type(device).__name__ and not device.canRecord:
            return False

        # All current, 'real' devices should support the COMMAND file
        # (but don't check; a user could have deleted it accidentally)
        return True


    def readResponse(self,
                     timeout: Optional[Union[int, float]] = None,
                     callback: Optional[Callable] = None) -> dict:
        """
        Helper to retrieve an EBML response from the device's `RESPONSE` file.

        :param timeout: Time to wait for a valid response.
        :param callback: A function to call each response-checking
            cycle. If the callback returns `True`, the wait for a response
            will be cancelled. The callback function should take no
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
                data = self.decode(raw)

                if 'EBMLResponse' not in data:
                    logger.warning('Response did not contain an EBMLResponse element')

                return data.get('EBMLResponse', data)

            except (AttributeError, IndexError, KeyError, TypeError) as err:
                # TODO: Better exception handling in readResponse()
                warnings.warn("Ignoring exception in {}.readResponse(): {!r}".format(type(self).__name__, err))

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
            Both are *NIX epoch time (seconds since 1970-01-01T00:00:00).
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


    def sendCommand(self,
                    cmd: dict,
                    response: bool = True,
                    timeout: float = 10,
                    interval: float = .25,
                    index: bool = True,
                    callback: Optional[Callable] = None) -> Union[None, dict]:
        """ Send a raw command to the device and (optionally) retrieve the
            response.

            :param cmd: The raw EBML representing the command.
            :param response: If `True`, wait for and return a response.
            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a
                response.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.

            @raise DeviceTimeout
        """
        if 'EBMLCommand' in cmd and index:
            self.index += 1
            cmd['EBMLCommand']['CommandIdx'] = self.index

        ebml = self.encode(cmd)

        now = time()
        deadline = now + timeout

        # Wait until the command queue is empty.
        # The file interface does this first.
        with self.device._busy:
            while response:  # a `while True` infinite loop
                data = self.readResponse()
                if data:
                    idx = data.get('ResponseIdx')
                    queueDepth = data.get('CMDQueueDepth', 1)
                    if queueDepth > 0:
                        break
                    raise DeviceTimeout("Timed out waiting for device to complete "
                                        "queued commands (%s remaining)" % queueDepth)
                else:
                    sleep(interval)

            self.writeCommand(ebml)

            if not response:
                return

            while time() <= deadline:
                if callback is not None and callback() is True:
                    return

                data = self.readResponse()

                if data and data.get("ResponseIdx") != idx:
                    return data

                sleep(interval)

            raise DeviceTimeout("Timed out waiting for command response (%s seconds)" % timeout)


    # =======================================================================
    # Firmware/Userpage/Bootloader updating
    # =======================================================================

    def _updateAll(self,
                   secure: bool = True,
                   wait: bool = True,
                   timeout: float = 10,
                   callback: Optional[Callable] = None) -> bool:
        """ Send the `"SecureUpdateAll"` command (or `"LegacyAll"` if the
            firmware is a simple binary rather than a signed package).

            :param secure: If `True`, use the `"SecureUpdateAll"` command
                instead of `"LegacyAll"`.
            :param wait: If `True`, wait for the recorer to dismount,
                indicating the command has executed.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
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
                       timeout: float = 1,
                       callback: Optional[Callable] = None) -> bool:
        """ Start the device recording, if supported.

            :param wait: If `True`, wait for the recorer to dismount,
                indicating the recording has started.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :returns: `True` if the command was successful.
        """
        if not self.device.canRecord:
            return False

        # FUTURE: Write commands wrapped in a <EBMLCommand> element?
        return self._runSimpleCommand({'RecStart': {}},
                                      timeoutMsg="Timed out waiting for recording to start",
                                      wait=wait,
                                      timeout=timeout,
                                      callback=callback)


    def reset(self,
              wait: bool = True,
              timeout: float = 10,
              callback: Optional[Callable] = None) -> bool:
        """ Reset (reboot) the recorder.

            :param wait: If `True`, wait for the recorer to dismount,
                indicating the reset has taken effect.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :returns: `True` if the command was successful.
        """
        # FUTURE: Write commands wrapped in a <EBMLCommand> element?
        return self._runSimpleCommand({'Reset': {}},
                                      timeoutMsg="Timed out waiting for device to reset",
                                      wait=wait,
                                      timeout=timeout,
                                      callback=callback)


# ===========================================================================
#
# ===========================================================================

#: A list of all `CommandInterface` types, used when finding a device's
#   interface. `FileCommandInterface` should go last. New interface types
#   defined elsewhere should append/insert themselves into this list.
INTERFACES = [SerialCommandInterface, FileCommandInterface]
