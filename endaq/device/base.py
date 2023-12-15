"""
Items common to all recorder types. Separate from module's `__init__.py` to
eliminate circular dependencies.
"""

__author__ = "dstokes"
__copyright__ = "Copyright 2023 Mide Technology Corporation"

from collections import defaultdict
from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import re
import struct
import sys
from threading import RLock
from time import struct_time
from typing import Any, AnyStr, Callable, Dict, Optional, Tuple, Union
import warnings

from idelib.dataset import Dataset, Channel
from idelib import importer
from idelib.parsers import CalibrationListParser, RecordingPropertiesParser
from idelib.transforms import Transform

import ebmlite
from ebmlite import MasterElement, loadSchema

if sys.platform == 'darwin':
    from . import macos as os_specific
elif 'win' in sys.platform:
    from . import win as os_specific
elif sys.platform == 'linux':
    from . import linux as os_specific

from . import config
from .config import ConfigInterface
from . import measurement
from .measurement import MeasurementType
from . import command_interfaces
from .exceptions import *
from .types import Drive, Filename, Epoch

logger = logging.getLogger('endaq.device')


__all__ = ('Recorder', 'os_specific')

# ===============================================================================
#
# ===============================================================================


class Recorder:
    """ A representation of an enDAQ/SlamStick data recorder. Some devices
        will instantiate as a specialized subclass, but the interface remains
        the same.
    """

    _INFO_FILE = os.path.join("SYSTEM", "DEV", "DEVINFO")
    _CLOCK_FILE = os.path.join("SYSTEM", "DEV", "CLOCK")
    _RECPROP_FILE = os.path.join("SYSTEM", "DEV", "DEVPROPS")
    _CONFIG_UI_FILE = os.path.join("SYSTEM", "CONFIG.UI")
    _COMMAND_FILE = os.path.join("SYSTEM", "DEV", "COMMAND")

    # Manifest and factory cal data on EFM32-based devices
    _USERPAGE_FILE = os.path.join("SYSTEM", "DEV", "USERPG%d")

    # Manifest and factory cal data on other devices (STM32)
    _SYSCAL_FILE = os.path.join("SYSTEM", "DEV", "syscal")
    _MANIFEST_FILE = os.path.join("SYSTEM", "DEV", "manifest")

    _CONFIG_FILE = os.path.join("SYSTEM", "config.cfg")
    _USERCAL_FILE = os.path.join("SYSTEM", "usercal.dat")
    _FW_UPDATE_FILE = os.path.join('SYSTEM', 'update.pkg')
    _RESPONSE_FILE = os.path.join('SYSTEM', 'DEV', 'RESPONSE')
    _BOOTLOADER_UPDATE_FILE = os.path.join("SYSTEM", 'boot.bin')
    _USERPAGE_UPDATE_FILE = os.path.join("SYSTEM", 'userpage.bin')
    _ESP_UPDATE_FILE = os.path.join('SYSTEM', 'esp32.bin')

    _TIME_PARSER = struct.Struct("<L")

    # TODO: This really belongs in the configuration UI
    _POST_CONFIG_MSG = ("When ready...\n"
                        "    1. Disconnect the recorder\n"
                        "    2. Mount to surface\n"
                        "    3. Press the recorder's primary button ")

    # These should eventually be read from the device
    SN_FORMAT = "%d"
    manufacturer = None
    homepage = None

    LIFESPAN = timedelta(2 * 365)
    CAL_LIFESPAN = timedelta(365)

    _NAME_PATTERN = re.compile(r'')


    def __init__(self, path: Optional[Filename], strict=True):
        """ Constructor. Typically, instantiation should be done indirectly,
            using functions such as `endaq.device.getDevices()` or
            `endaq.device.fromRecording()`. Explicitly instantiating a
            `Recorder` or `Recorder` subclass is rarely (if ever) necessary.

            :param path: The filesystem path to the recorder, or `None` if
                it is a 'virtual' device (e.g., constructed from data in a
                recording).
            :param strict: If `True`, only allow real device paths. If
                `False`, allow any path that contains the standard contents
                of a recorder's ``SYSTEM`` directory. Primarily for testing.
        """
        # self.mideSchema = loadSchema("mide_ide.xml")
        # self.manifestSchema = loadSchema("mide_manifest.xml")

        self._busy = RLock()
        self.strict = strict

        self._command = None
        self._path = None
        self.refresh(force=True)
        self.path = path

        # The source IDE `Dataset` used for 'virtual' devices.
        self._source = None


    @property
    def command(self):
        """ The device's "command interface," the means through which to
            directly control the device. Only applicable to non-virtual
            recorders (i.e., actual hardware, not instantiated from a
            recording).
        """
        # This property provides the appropriate exceptions common to
        # all attempts to send commands if the device is virtual, or
        # otherwise does not have a command interface.
        if self.isVirtual:
            raise UnsupportedFeature("Virtual devices cannot execute commands")

        with self._busy:
            if self._command is None:
                for interface in command_interfaces.INTERFACES:
                    if interface.hasInterface(self):
                        # logger.debug('Instantiating command interface: {!r}'.format(interface))
                        self._command = interface(self)
                        break

                if self._command is None:
                    raise UnsupportedFeature("Device has no command interface")

            return self._command


    @command.setter
    def command(self, interface):
        with self._busy:
            if interface == self._command:
                return
            if self._command is not None:
                with self._busy:
                    self._command.close()
            self._command = interface


    @property
    def hasCommandInterface(self) -> bool:
        """ Does the device have the ability to execute commands?
        """
        if self.isVirtual:
            return False
        try:
            return bool(self.command)
        except UnsupportedFeature:
            return False


    @property
    def available(self) -> bool:
        """ Is the device mounted and available as a drive?
        """
        if self.isVirtual or not self.path:
            return False

        # Two checks, since former is a property that sets latter
        # and path itself isn't a reliable test in Linux
        return (os.path.exists(self.path)
                and os.path.isfile(self.infoFile))


    def __repr__(self):
        path = self._path or "virtual"
        if self.name:
            name = '{} "{}"'.format(self.partNumber, self.name)
        else:
            name = self.partNumber
        return '<{} {} SN:{} ({})>'.format(type(self).__name__, name, self.serial, path)


    @classmethod
    def _getHash(cls, path: Filename, info=None) -> int:
        """ Calculate the device's hash. Separated from `__hash__()` so it
            can be used by `getDevices()` to find known recorders.

            :param path: The device's filesystem path.
            :param info: The contents of the device's `DEVINFO` file, if
                previously loaded. For future caching optimization.
        """
        if path and not info:
            path = os.path.realpath(path.path if isinstance(path, Drive) else path)
            infoFile = os.path.join(path, cls._INFO_FILE)
            if os.path.exists(infoFile):
                with open(infoFile, 'rb') as f:
                    info = f.read()

        return hash(info)


    def __hash__(self) -> int:
        """ Return hash(self). """
        with self._busy:
            if self._hash is None:
                self.getInfo()
            return self._hash


    def refresh(self, force=False):
        """ Clear cached device information, ensuring the data is up-to-date.
        """
        with self._busy:
            if self._path and not force:
                return
            self._info = None
            self._hash = None
            self._config = None
            self._sn = None
            self._snInt = None
            self._chipId = None
            self._sensors = None
            self._channels = None
            self._channelRanges = {}
            self._manifest = None
            self._calibration = None
            self._calData = None  # Note: unlike _manData, _calData is raw
            self._calPolys = None
            self._userCalPolys = None
            self._userCalDict = None
            self._factoryCalPolys = None
            self._factoryCalDict = None
            self._properties = None
            self._volumeName = None
            self._wifi = None  # Cached name of the manifest's Wi-Fi element

            if self._command:
                try:
                    self._command.close()
                except (AttributeError, IOError) as err:
                    logger.debug('Ignoring exception closing {}: '
                                 '{!r}'.format(self._command, err))
                self._command = None

            self._configInterface = None


    @property
    def path(self) -> Union[str, None]:
        with self._busy:
            return self._path


    @path.setter
    def path(self, dev: Union[Filename, None]):
        """ The recorder's filesystem path (e.g., drive letter or mount point).
        """
        with self._busy:
            if dev is not None:
                if self.strict and not self.isRecorder(dev):
                    raise IOError("Specified path isn't a %s: %r" %
                                  (self.__class__.__name__, dev))

                path = os.path.realpath(dev.path if isinstance(dev, Drive) else dev)
                self.configFile = os.path.join(path, self._CONFIG_FILE)
                self.infoFile = os.path.join(path, self._INFO_FILE)
                self.clockFile = os.path.join(path, self._CLOCK_FILE)
                self.userCalFile = os.path.join(path, self._USERCAL_FILE)
                self.configUIFile = os.path.join(path, self._CONFIG_UI_FILE)
                self.recpropFile = os.path.join(path, self._RECPROP_FILE)
                self.commandFile = os.path.join(path, self._COMMAND_FILE)
                self._volumeName = None
            else:
                path = None
                self._volumeName = ''
                self.configFile = self.infoFile = None
                self.clockFile = self.userCalFile = self.configUIFile = None
                self.recpropFile = self.commandFile = None

            self._path = path


    @property
    def volumeName(self):
        """ The recorder's user-specified filesystem label. """
        if self.isVirtual:
            return False

        if self._path and self._volumeName is None:
            try:
                self._volumeName = os_specific.getDriveInfo(self.path).label
            except (AttributeError, IOError, TypeError) as err:
                logger.debug("Getting volumeName raised a possibly-allowed exception: %r" % err)
        return self._volumeName


    def __eq__(self, other) -> bool:
        """ x.__eq__(y) <==> x==y """
        if self is other:
            return True
        return hash(self) == hash(other)


    @classmethod
    def _matchName(cls, name: AnyStr) -> bool:
        """ Does a given product name match this device type?
        """
        if isinstance(name, bytes):
            name = str(name, 'utf8')
        return bool(cls._NAME_PATTERN.match(name))


    @classmethod
    def isRecorder(cls,
                   path: Filename,
                   strict: bool = True,
                   **kwargs) -> bool:
        """ Test whether a given filesystem path refers to the root directory
            of a data recorder.

            :param path: The path to the possible recording device (e.g. a
                mount point under Linux/BSD/etc., or a drive letter under
                Windows)
            :param strict: If `False`, only the directory structure is used
                to identify a recorder. If `True`, non-FAT file systems will
                be automatically rejected.
        """
        # FUTURE: Have this actually return the hash if it is a recorder?
        #  It would still work in conditionals, and can be reused by
        #  `getDevices()`.

        try:
            if isinstance(path, Drive):
                path, _volumeName, _sn, fs, _dtype = path
            else:
                fs = ''

            path = os.path.realpath(path)
            infoFile = os.path.join(path, cls._INFO_FILE)

            if strict:
                if not fs:
                    info = os_specific.getDriveInfo(path)
                    if not info:
                        return False
                    fs = info.fs
                if "fat" not in fs.lower():
                    return False

            if 'info' in kwargs:
                devinfo = loadSchema('mide_ide.xml').loads(kwargs['info']).dump()
            elif os.path.isfile(infoFile):
                with loadSchema('mide_ide.xml').load(infoFile) as doc:
                    devinfo = doc.dump()
            else:
                return False

            props = devinfo['RecordingProperties']['RecorderInfo']
            name = props['ProductName']
            if isinstance(name, bytes):
                # In ebmlite < 3.1, StringElements are read as bytes.
                name = str(name, 'utf8')

            return cls._matchName(name)

        except (KeyError, TypeError, AttributeError, IOError) as err:
            logger.debug("isRecorder() raised a possibly-allowed exception: %r" % err)
            pass

        return False


    def getInfo(self,
                name: Optional[str] = None,
                default=None) -> Any:
        """ Retrieve a recorder's device information. Returns either a single
            item or a dictionary of all device information.

            :keyword name: The name of a specific device info item. `None`
                will return the entire dictionary of device information.
            :keyword default: A value to return, if the device has no
                information, or, if `name` is used, the device does not have a
                specific item.
            :return: If no `name` is specified, a dictionary containing the
                device data. If a `name` is specified, the type returned will
                vary.
        """
        mideSchema = loadSchema("mide_ide.xml")
        with self._busy:
            if self._info is None:
                if self.path is not None:
                    with open(self.infoFile, 'rb') as f:
                        data = f.read()
                    self._hash = self._getHash(self.path, data)
                    infoFile = mideSchema.loads(data)
                    try:
                        props = infoFile.dump().get('RecordingProperties', '')
                        if 'RecorderInfo' in props:
                            self._info = props.get('RecorderInfo', {})
                            for k, v in self._info.items():
                                if isinstance(v, bytes):
                                    # Nothing in the device info should be binary,
                                    # but as of ebmlite 3.0.1, StringElements are
                                    # read as bytes. Convert.
                                    self._info[k] = str(v, 'utf8')
                    except (IOError, KeyError) as err:
                        logger.debug("getInfo() raised a possibly-allowed exception: %r" % err)
                        pass
                    finally:
                        infoFile.close()

            if not self._hash:
                # Probably a virtual device (from IDE file); use _info dict.
                # FUTURE: base hash on IDE?
                self._hash = hash(repr(self._info))

            if not self._info:
                if name is None:
                    return {}
                return default

            if name is None:
                # Whole dict requested: return a copy (prevents accidental edits)
                return self._info.copy()
            else:
                return self._info.get(name, default)


    @property
    def isVirtual(self):
        """ Is this actual hardware, or a virtual recorder? """
        # NOTE: This will need revision in the future if/when we have
        #  actual recorders connected remotely by other means.
        return self.path is None


    @property
    def name(self) -> str:
        """ The recording device's (user-assigned) name. """
        try:
            return self.config.name
        except (AttributeError, KeyError, UnsupportedFeature):
            return ''


    @property
    def notes(self) -> str:
        """ The recording device's (user-assigned) description. """
        try:
            return self.config.notes
        except (AttributeError, KeyError, UnsupportedFeature):
            return ''


    @property
    def productName(self) -> str:
        """ The recording device's manufacturer-issued name. """
        return self.getInfo('ProductName', '')


    @property
    def partNumber(self):
        """ The recording device's manufacturer-issued part number.
        """
        return self.getInfo('PartNumber', '')


    @property
    def serial(self) -> str:
        """ The recorder's manufacturer-issued serial number (as string). """
        if self._sn is None:
            self._snInt = self.getInfo('RecorderSerial', None)
            if self._snInt is None:
                self._sn = ""
            else:
                self._sn = self.SN_FORMAT % self._snInt
        return self._sn


    @property
    def serialInt(self) -> Union[int, None]:
        """ The recorder's manufacturer-issued serial number (as integer). """
        _ = self.serial  # Calls property, which sets _snInt attribute
        return self._snInt


    @property
    def mcuType(self):
        """ The recorder's CPU/MCU type. """
        return self.getInfo('McuType', None)


    @property
    def chipId(self) -> Union[int, None]:
        """ The recorder CPU/MCU unique chip ID. """
        if self._chipId is None:
            info = self.getInfo()

            # IDs 64 bits or shorter can be a UniqueChipID (UnsignedInteger).
            # Longer IDs (e.g., on STM32) are stored in a UniqueChipIDLong
            # (BinaryElement), big-endian.
            if 'UniqueChipIDLong' in info:
                chid = 0
                for b in bytearray(info['UniqueChipIDLong']):
                    chid = (chid << 8) | b
                self._chipId = chid
            elif 'UniqueChipID' in info:
                self._chipId = info['UniqueChipID']
            else:
                return None

        return self._chipId


    @property
    def hardwareVersion(self) -> str:
        """ The recorder's manufacturer-issued hardware version number. Newer
            version numbers will be split into *version*, *revision*, and
            (optionally) a `BOM version` letter. Older versions will be
            a single number.
        """
        rev = self.hardwareVersionInt
        try:
            if rev > 99:
                # New structure of HwRev, which includes version, revision,
                # and BOM version.
                major = int(rev/10000)
                minor = int((rev % 10000) / 100)
                bom = rev % 100
                if bom == 0:
                    bom = ""
                elif bom < 26:
                    bom = chr(bom+65)
                else:
                    bom = chr((bom % 25) + 64) * int((bom // 25 + 1))
                rev = f"v{major}r{minor}{bom}"
        except TypeError:
            pass
        return str(rev)


    @property
    def hardwareVersionInt(self) -> int:
        """ The recorder's manufacturer-issued hardware version number.
        """
        return self.getInfo('HwRev', -1)

    @property
    def firmwareVersion(self) -> int:
        """ The recorder's manufacturer-issued firmware version number.
        """
        return self.getInfo('FwRev', -1)


    @property
    def firmware(self) -> Union[str, None]:
        """ The recorder's manufacturer-issued firmware version string or name.
        """
        fw = self.getInfo('FwRevStr', None)
        if not fw:
            # Older FW did not write FwRevStr
            fw = "1.%s" % self.firmwareVersion
        return fw


    @property
    def timestamp(self) -> Union[int, None]:
        """ The recorder's date of manufacture, epoch time. """
        return self.getInfo('DateOfManufacture')


    @property
    def birthday(self) -> Union[datetime, None]:
        """ The recorder's date of manufacture. """
        bd = self.getInfo('DateOfManufacture')
        if bd is not None:
            return datetime.utcfromtimestamp(bd)

    
    @property
    def postConfigMsg(self) -> str:
        """ The message to be displayed after configuration. """
        if not self.isVirtual and self.config and self.config.postConfigMsg:
            return self.config.postConfigMsg
        return self._POST_CONFIG_MSG


    @property
    def canRecord(self) -> bool:
        """ Can the device record on command? """
        if not self.hasCommandInterface:
            return False

        return self.command.canRecord


    @property
    def canCopyFirmware(self) -> bool:
        """ Can the device get new firmware/userpage from a file? """
        if not self.hasCommandInterface:
            return False

        return self.command.canCopyFirmware


    @property
    def hasWifi(self) -> bool:
        """ The name of the Wi-Fi hardware type, or `False` if none. The name
            will not be blank, so expressions like `if dev.hasWifi:` will work.
        """
        if not self.hasCommandInterface:
            return False
        if self._wifi is None:
            man = self.getManifest()
            if not man:
                self._wifi = False
            else:
                for k in man.keys():
                    if "CommunicationWiFi" in k:
                        self._wifi = k
                        break
        return self._wifi


    def getSubchannelRange(self,
                           subchannel: Channel,
                           rounded: bool = True) -> tuple:
        """ Get the range of one of the device's subchannels. Note that the
            reported range (particularly for digital sensors) is that of the
            subchannel's parser, and may exceed values actually produced by
            the sensor.

            :param subchannel: An `idelib.dataset.SubChannel` instance,
                e.g., from the recorder's `channels` dictionary.
            :param rounded: If `True`, round the results to two significant
                digits (to remove floating point rounding errors).
        """
        # XXX: WIP
        key = (subchannel.parent.id, subchannel.id)
        if key in self._channelRanges:
            return self._channelRanges[key]

        xforms = self.getCalPolynomials()
        lo, hi = subchannel.displayRange

        for xformId in subchannel.getTransforms():
            if isinstance(xformId, Transform):
                xform = xformId
            elif xformId not in xforms:
                continue
            else:
                xform = xforms[xformId]

            lo = xform.function(lo)
            hi = xform.function(hi)

        # HACK: The old parser minimum is slightly low; use negative max.
        lo = -hi

        if rounded:
            lo, hi = (float("%.2f" % lo), float("%.2f" % hi))

        self._channelRanges[key] = (lo, hi)

        return self._channelRanges[key]


    def getAccelRange(self,
                      channel: Optional[int] = None,
                      subchannel: Optional[int] = None,
                      rounded: bool = True) -> tuple:
        """ Get the range of the device's acceleration measurement.

            :param channel: The accelerometer's channel ID.
            :param subchannel: The accelerometer axis' subchannel ID.
            :param rounded: If `True`, get the sensor's acceleration
                range, ignoring any effect of the sensor's resolution.
        """
        # TODO: This can be made more general and be used for any channel.
        # TODO: Make this fall back to the AnalogSensorScaleHintF?

        channel = 8 if channel is None else channel
        subchannel = 0 if subchannel is None else subchannel

        channels = self.getChannels(measurement.ACCELERATION)
        xforms = self.getCalPolynomials()

        if not channels:
            raise ConfigError("Could not read any accelerometer channels from device!")
        if not xforms:
            raise ConfigError("Could not read any transform/calibration polynomials from device!")

        if channel not in channels:
            for chid in (8, 80, 32):
                if chid in channels:
                    channel = chid
                    break
        if channel is None:
            channel = list(channels.keys())[0]

        key = (channel, subchannel)

        if key in self._channelRanges:
            return self._channelRanges[key]

        ch = channels[channel]
        subch = ch[subchannel]
        sens = subch.sensor
        if isinstance(sens, int):
            sens = self.sensors.get(sens, None)
        if not sens:
            raise ConfigError("Could not find sensor for {}".format(subch))

        # Digital sensors. The parser's struct range doesn't necessarily
        # reflect the actual measured range.
        # TODO: Refactor this; it's brittle
        sname = sens.name

        if 'ADXL' in sname:
            for name, lo, hi in (('ADXL345', -16, 16),
                                 ('ADXL355', -8, 8),
                                 ('ADXL357', -40, 40),
                                 ('ADXL375', -200, 200)):
                if name in sname:
                    self._channelRanges[key] = (lo, hi)
                    return lo, hi

        xform = None
        if isinstance(ch.transform, int):
            try:
                xform = xforms[ch.transform]
            except KeyError:
                raise ConfigError("No such transform polynomial ID %r" %
                                  ch.transform)

        r = ch.displayRange[subchannel]
        hi = xform.function(r[1]) if xform else r[1]

        # HACK: The old parser minimum is slightly low; use negative max.
        # lo = xform.function(r[0]) if xform else r[0]
        lo = -hi

        if rounded:
            self._channelRanges[key] = (float("%.2f" % lo), float("%.2f" % hi))
        else:
            self._channelRanges[key] = (lo, hi)

        return self._channelRanges[key]


    def getAccelAxisChannels(self) -> dict:
        """ Retrieve a list of all accelerometer axis subchannels, ordered
            alphabetically (X, Y, Z).

            :returns: A dictionary of accelerometer subchannels, keyed by
                parent channel ID.
        """
        channels = defaultdict(list)

        for subCh in self.getSubchannels(measurement.ACCELERATION):
            channels[subCh.parent.id].append(subCh)

        return {chId: sorted(subChs, key=lambda x: x.axisName)
                for chId, subChs in channels.items()}


    def getTime(self, epoch=True) -> Union[Tuple[datetime, datetime], Tuple[Epoch, Epoch]]:
        """ Read the date/time from the device.

            :param epoch: If `True`, return the date/time as integer seconds
                since the epoch ('Unix time'). If `False`, return a Python
                `datetime.datetime` object.
            :return: The system time and the device time. Both are UTC.
        """
        if self.isVirtual or not self.path:
            raise UnsupportedFeature('Virtual devices do not have clocks')

        if self.hasCommandInterface:
            return self.command.getTime(epoch=epoch)
        else:
            ci = command_interfaces.FileCommandInterface(self)
            return ci.getTime(epoch=epoch)


    def setTime(self,
                t: Union[Epoch, datetime, struct_time, tuple, None] = None,
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
            :return: The time that was set, as integer seconds since the epoch.
        """
        if self.isVirtual or not self.path:
            raise UnsupportedFeature('Virtual devices do not have clocks')

        if self.hasCommandInterface:
            return self.command.setTime(t=t, pause=pause, retries=retries)
        else:
            ci = command_interfaces.FileCommandInterface(self)
            return ci.setTime(t=t, pause=pause, retries=retries)


    def getClockDrift(self,
                      pause: bool = True,
                      retries: int =1 ) -> float:
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
        if self.isVirtual or not self.path:
            raise UnsupportedFeature('Virtual devices do not have clocks')

        if self.hasCommandInterface:
            return self.command.getClockDrift(pause=pause, retries=retries)
        else:
            ci = command_interfaces.FileCommandInterface(self)
            return ci.getClockDrift(pause=pause, retries=retries)


    def _parsePolynomials(self, cal: MasterElement) -> Dict[int, Transform]:
        """ Helper method to parse CalibrationList EBML into `Transform`
            objects.
        """
        try:
            parser = CalibrationListParser(None)
            calPolys = parser.parse(cal[0])
            if calPolys:
                calPolys = {p.id: p for p in calPolys if p is not None}
            return calPolys
        except (KeyError, IndexError, ValueError) as err:
            logger.debug("_parsePolynomials() raised a possibly-allowed exception: %r" % err)
            pass


    def _readUserpage(self) -> Union[dict, None]:
        """ Read the device's manifest data from the EFM32 'userpage'. The
            data is a superset of the information returned by `getInfo()`.
            Factory calibration and recorder properties are also read
            and cached, since one or both are in the userpage.
        """
        if self._manifest is not None:
            return self._manifest

        # Recombine all the 'user page' files
        data = bytearray()
        for i in range(4):
            filename = os.path.join(self.path, self._USERPAGE_FILE % i)
            with open(filename, 'rb') as fs:
                data.extend(fs.read())

        (manOffset, manSize,
         calOffset, calSize,
         propOffset, propSize) = struct.unpack_from("<HHHHHH", data)

        manData = data[manOffset:manOffset + manSize]
        calData = data[calOffset:calOffset + calSize]

        # _propData is read and cached here but parsed in `getSensors()`.
        # New devices use a dynamically-generated properties file, which
        # overrides any property data in the USERPAGE.
        if os.path.exists(self.recpropFile):
            with open(self.recpropFile, 'rb') as f:
                self._propData = f.read()
        else:
            # Zero offset means no property data (very old devices). For new
            # devices, a size of 1 also means no data (it's a null byte).
            propSize = 0 if (propOffset == 0 or propSize <= 1) else propSize
            self._propData = data[propOffset:propOffset + propSize]

        try:
            self._manData = loadSchema("mide_manifest.xml").loads(manData)
            self._manifest = self._manData.dump().get('DeviceManifest')

            self._calData = loadSchema("mide_ide.xml").loads(calData)
            self._calibration = self._calData.dump().get('CalibrationList')

        except (AttributeError, KeyError) as err:
            logger.debug("_readUserpage() raised a possibly-allowed exception: %r" % err)
            pass

        return self._manifest


    def _readManifest(self) -> Union[dict, None]:
        """ Read the device's manifest data from the 'MANIFEST' file. The
            data is a superset of the information returned by `getInfo()`.

            Factory calibration and recorder properties are also read and
            cached for backwards compatibility, since both are in the older
            devices' EFM32 'userpage'.
        """
        manFile = os.path.join(self.path, self._MANIFEST_FILE)
        calFile = os.path.join(self.path, self._SYSCAL_FILE)

        try:
            with open(manFile, 'rb') as f:
                self._manData = loadSchema("mide_manifest.xml").loads(f.read())
            self._manifest = self._manData.dump().get('DeviceManifest')
        except (FileNotFoundError, AttributeError, KeyError) as err:
            logger.debug(f"Possibly-allowed exception when reading {manFile}: {err!r}")

        try:
            with loadSchema("mide_ide.xml").load(calFile) as doc:
                self._calData = doc.schema.loads(doc.getRaw())
                self._calibration = self._calData[0].dump()
        except (FileNotFoundError, AttributeError, IndexError) as err:
            logger.debug(f"Possibly-allowed exception when reading {calFile}: {err!r}")

        try:
            # _propData is read and cached here but parsed in `getSensors()`.
            # Old EFM32 recorders stored this w/ the manifest in the USERPAGE.
            with open(self.recpropFile, 'rb') as f:
                self._propData = f.read()
        except (FileNotFoundError, AttributeError, KeyError) as err:
            logger.debug(f"Possibly-allowed exception when reading {self.recpropFile}: {err!r}")

        return self._manifest


    def getManifest(self) -> Union[dict, None]:
        """ Read the device's manifest data. The data is a superset of the
            information returned by `getInfo()`.
        """
        with self._busy:
            if self.isVirtual or self._manifest is not None:
                return self._manifest

            if os.path.exists(os.path.join(self.path, self._MANIFEST_FILE)):
                self._readManifest()
            elif os.path.exists(os.path.join(self.path, self._USERPAGE_FILE % 0)):
                self._readUserpage()

            return self._manifest


    def getUserCalibration(self,
                           filename: Optional[Filename] = None) -> Union[dict, None]:
        """ Get the recorder's user-defined calibration data as a dictionary
            of parameters.
        """
        if self.isVirtual:
            return self._userCalDict

        filename = self.userCalFile if filename is None else filename
        if filename is None or not os.path.exists(filename):
            return None
        if filename != self.userCalFile:
            self._userCalDict = None

        if self._userCalDict is None:
            with open(self.userCalFile, 'rb') as f:
                d = loadSchema("mide_ide.xml").load(f).dump()
                self._userCalDict = d.get('CalibrationList', None)
        return self._userCalDict


    def getUserCalPolynomials(self,
                              filename: Optional[Filename] = None) -> Union[dict, None]:
        """ Get the recorder's user-defined calibration data as a dictionary
            of `idelib.transforms.Transform` subclass instances, keyed by ID.

            :param filename: The name of an alternative user calibration
                `.dat` file to read (as opposed to the device's standard
                user calibration).
        """
        if self.isVirtual and not filename:
            return None

        filename = self.userCalFile if filename is None else filename
        if filename is None or not os.path.exists(filename):
            return None
        if self._userCalPolys is None:
            with loadSchema('mide_ide.xml').load(filename) as doc:
                self._userCalPolys = self._parsePolynomials(doc)
        return self._userCalPolys


    def getCalibration(self, user: bool = True) -> Union[dict, None]:
        """ Get the recorder's current calibration information. User-supplied
            calibration, if present, takes priority (as it is what will be
            applied in recordings).

            :param user: If `False`, ignore user calibration and return
                factory calibration.
        """
        if user:
            c = self.getUserCalibration()
            if c is not None:
                return c

        self.getManifest()
        return self._calibration


    def getCalPolynomials(self, user: bool = True) -> Union[dict, None]:
        """ Get the constructed Polynomial objects created from the device's
            current calibration data, as a dictionary of
            `idelib.transform.Transform` subclass instances, keyed by ID.
            User-supplied calibration, if present, takes priority (as it is
            what will be applied in recordings).

            :param user: If `False`, ignore user calibration and return
                factory calibration.
        """
        if user:
            c = self.getUserCalPolynomials()
            if c is not None:
                return c

        self.getSensors()
        if self._calPolys is None:
            self._calPolys = self._parsePolynomials(self._calData)

        return self._calPolys


    def getCalDate(self,
                   user: bool = False,
                   epoch: bool = False) -> Union[datetime, Epoch, None]:
        """ Get the date of the recorder's calibration. By default,
            the factory calibration date is returned, as user calibration
            typically has no date.

            :param user: If `False` (default), only return the factory-set
                calibration date. If `True`, return the date of the
                user-applied calibration (if any).
            :param epoch: If `False` (default), return the calibration date
                as a Python `datetime.datetime` object. If `False`, return
                the calibration date as epoch time (i.e., a UNIX timestamp).
                For backwards compatibility with earlier software.
        """
        data = self.getCalibration(user=user)
        if data:
            cd = data.get('CalibrationDate', None)
            if cd is not None and not epoch:
                return datetime.utcfromtimestamp(cd)
            return cd
        return None


    def _getCalExpiration(self, data) -> Union[Epoch, None]:
        """ Get the expiration date of the recorder's factory calibration.
        """
        if data is None:
            return None
        caldate = data.get('CalibrationDate', None)
        calexp = data.get('CalibrationExpiry', None)

        if caldate is None and calexp is None:
            return None

        if isinstance(calexp, int) and calexp > caldate:
            return calexp

        return caldate + self.CAL_LIFESPAN.total_seconds()


    def getCalExpiration(self, user=False, epoch=False) -> Union[datetime, Epoch, None]:
        """ Get the expiration date of the recorder's calibration. Defaults
            to the expiration date of the factory calibration; user-supplied
            calibration typically has no expiration date.

            :param user: If `False` (default), only return the factory-set
                calibration expiration date. If `True`, return the expiration
                date of the user-applied calibration (if any).
            :param epoch: If `False` (default), return the expiration date as
                a Python `datetime.datetime` object. If `False`, return the
                expiration date as epoch time (i.e., a UNIX timestamp). For
                backwards compatibility with earlier software.
        """
        ce = self._getCalExpiration(self.getCalibration(user=user))
        if ce is not None and not epoch:
            return datetime.utcfromtimestamp(ce)
        return ce


    def getCalSerial(self, user=False) -> Union[int, None]:
        """ Get the recorder's factory calibration serial number. Defaults
            to the serial number of the factory calibration; the serial
            number of user-supplied calibration is typically zero or
            totally absent.

            :param user: If `False` (default), only return the factory-set
                calibration serial number. If `True`, return the serial
                number of the user-applied calibration (if any).
        """
        data = self.getCalibration(user=user)
        if data:
            return data.get('CalibrationSerialNumber', None)
        return None


    @property
    def transforms(self) -> Union[dict, None]:
        """ The recorder's calibration polynomials, a dictionary of
            `idelib.transform.Transform` subclass instances keyed by ID. For
            compatibility with `idelib.dataset.Dataset`; results are the
            same as `Recorder.getCalPolynomials()`.
        """
        return self.getCalPolynomials()


    def getProperties(self) -> dict:
        """ Get the raw Recording Properties from the device.
        """
        if self.isVirtual or self._properties is not None:
            return self._properties

        self.getManifest()
        props = loadSchema("mide_ide.xml").loads(self._propData).dump()

        self._properties = props.get('RecordingProperties', {})
        return self._properties


    def getSensors(self) -> dict:
        """ Get the recorder sensor description data.
        """
        self.getManifest()

        if self._sensors is not None:
            return self._sensors

        # Use dataset parsers to read the recorder properties.
        # This also caches the channels, polynomials, and warning ranges.
        # This is nice in theory but kind of ugly in practice.
        try:
            doc = Dataset(None)
            if not self._propData:
                # No recorder property data; use defaults
                doc.recorderInfo = self.getInfo()
                importer.createDefaultSensors(doc)
                if 0 in doc.channels:
                    doc.transforms.setdefault(0, doc.channels[0].transform)
            else:
                # Parse userpage recorder property data
                parser = RecordingPropertiesParser(doc)
                doc._parsers = {'RecordingProperties': parser}
                parser.parse(loadSchema("mide_ide.xml").loads(self._propData)[0])
            self._channels = doc.channels
            self._sensors = doc.sensors
            self._warnings = doc.warningRanges
        except (IndexError, AttributeError) as err:
            # TODO: Report the error. Right now, this fails silently on bad
            #  data (e.g. the number of subchannels doesn't match a channel
            #  parser.
            logger.debug("getSensors() raised a possibly-allowed exception: %r" % err)
            pass

        return self._sensors


    @property
    def sensors(self) -> dict:
        return self.getSensors()


    @property
    def channels(self) -> dict:
        self.getSensors()
        return self._channels.copy()


    def getChannels(self, mtype: Union[MeasurementType, str, None] = None) -> dict:
        """ Get the recorder channel description data.

            :param mtype: An optional measurement type, to filter results.
            :return: A dictionary of `Channel` objects, keyed by channel ID.
        """
        # `getSensors()` does all the real work
        self.getSensors()
        if mtype:
            channels = measurement.filter_channels(self._channels, mtype)
            return {ch.id: ch for ch in channels}
        else:
            return self._channels.copy()


    def getSubchannels(self, mtype: Union[MeasurementType, str, None] = None) -> dict:
        """ Get the recorder subchannel description data.

            :param mtype: An optional measurement type, to filter results. See
                `endaq.device.measurement`.
            :return: A list of `SubChannel` objects.
        """
        # `getSensors()` does all the real work
        self.getSensors()
        channels = []
        for ch in self._channels.values():
            if ch.children:
                channels.extend(ch.children)
        if mtype:
            channels = measurement.filter_channels(channels, mtype)

        return channels


    @classmethod
    def generateCalEbml(cls,
                        transforms: dict,
                        date: Optional[int] = None,
                        expires: Optional[int] = None,
                        calSerial: int = 0) -> ebmlite.Document:
        """ Generate binary calibration data (EBML). For the keyword arguments,
            a value of `False` will simply not write the corresponding element.

            :param transforms: A dictionary or list of `idelib.calibration`
                objects.
            :param date: The date of calibration (epoch timestamp).
            :param expires: The calibration expiration date (epoch timestamp).
            :param calSerial: The calibration serial number (integer). 0 is
                assumed to be user-created calibration.
        """
        if isinstance(transforms, dict):
            transforms = transforms.values()

        data = {}
        for xform in transforms:
            if xform.id is None:
                continue
            n = "%sPolynomial" % xform.__class__.__name__
            data.setdefault(n, []).append(xform.asDict())

        if date:
            data['CalibrationDate'] = int(date)
        if expires:
            data['CalibrationExpiry'] = int(expires)
        if isinstance(calSerial, int):
            data['CalibrationSerialNumber'] = calSerial

        return loadSchema('mide_ide.xml').encodes({'CalibrationList': data})


    def writeUserCal(self,
                     transforms: dict,
                     filename: Union[str, Path, None] = None):
        """ Write user calibration to the SSX.

            :param transforms: A dictionary or list of `idelib.calibration`
                objects.
            :param filename: An alternate file to which to write the data,
                instead of the standard user calibration file.
        """
        if self.isVirtual:
            raise ConfigError('Could not write user calibration data: '
                              'Not a real recorder!')

        filename = self.userCalFile if filename is None else filename
        cal = self.generateCalEbml(transforms)
        with open(filename, 'wb') as f:
            f.write(cal)


    # ===========================================================================
    #
    # ===========================================================================

    def startRecording(self,
                       timeout: float = 1,
                       callback: Optional[Callable] = None) -> bool:
        """ Start the device recording, if supported.

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :returns: `True` if the command was successful.
        """
        # FUTURE: Remove Recorder.startRecording()
        warnings.warn("Direct control should be done through the 'command' attribute",
                      DeprecationWarning)

        return self.command.startRecording(timeout=timeout, callback=callback)


    # ===========================================================================
    #
    # ===========================================================================

    @property
    def config(self) -> ConfigInterface:
        """ The device's "configuration interface," the means through which to
            read and/or write device config.
        """
        with self._busy:
            if self._configInterface is None:
                for interface in config.INTERFACES:
                    if interface.hasInterface(self):
                        # logger.debug('Instantiating config interface: {!r}'.format(interface))
                        self._configInterface = interface(self)
                        break

                if self._configInterface is None:
                    raise UnsupportedFeature("Device has no configuration interface")

            return self._configInterface


    @config.setter
    def config(self, interface: ConfigInterface):
        with self._busy:
            self._configInterface = interface


    @property
    def hasConfigInterface(self) -> bool:
        """ Does the device have the ability to execute commands?
        """
        try:
            return bool(self.config)
        except UnsupportedFeature:
            return False


    # ===========================================================================
    #
    # ===========================================================================

    @classmethod
    def fromRecording(cls, dataset: Dataset) -> "Recorder":
        """ Create a 'virtual' recorder from the recorder description in a
            recording.
        """
        dev = cls(None)
        dev._source = dataset
        dev._info = dataset.recorderInfo.copy()
        dev._calPolys = dataset.transforms.copy()
        dev._channels = dataset.channels.copy()
        dev._warnings = dataset.warningRanges.copy()
        dev._sensors = dataset.sensors.copy()

        # Crawl the Dataset's EBML document for config-related data.
        # Usually pretty quick.
        for el in dataset.ebmldoc:
            if el.name.endswith('DataBlock'):
                # End of the metadata
                break
            elif el.name.startswith('RecorderConfiguration'):
                # This will eventually be unnecessary; see issue:
                # https://github.com/MideTechnology/idelib/issues/112
                dev._config = dataset.ebmldoc.schema.loads(el.getRaw())
            elif el.name == 'ConfigUI':
                # Proposed, but not yet in IDE files.
                # No longer strictly required due to `ui_defaults`.
                dev._configUi = loadSchema('mide_config_ui.xml').loads(el.value)

        # Datasets merge calibration info into recorderInfo; separate them.
        dev._calibration = {}
        for k in ('CalibrationDate',
                  'CalibrationExpiry',
                  'CalibrationSerialNumber'):
            v = dev._info.pop(k, None)
            if v is not None:
                dev._calibration[k] = v

        return dev
