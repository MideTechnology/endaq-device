"""
'Strategy' classes for reading device information over different media
(e.g., file-based or through the command interface). These are similar to
`CommandInterface` and `ConfigInterface` in that regard, but these are not
accessed directly.
"""

from abc import ABC, abstractmethod
import logging
import os.path
import struct
from typing import Optional, Tuple, Union, TYPE_CHECKING

from .types import Drive, Filename
from .command_interfaces import SerialCommandInterface
from .exceptions import UnsupportedFeature
from . import util

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .base import Recorder


# ===========================================================================
#
# ===========================================================================

class DeviceInfo(ABC):
    """
    An abstract mechanism for retrieving and setting device information. Its
    methods only read and write the raw binary; any parsing and/or is done by
    the caller.
    """

    @classmethod
    @abstractmethod
    def hasInterface(cls, device: "Recorder") -> bool:
        """ Determine if a device supports this info-accessing type.

            :param device: The recorder to check.
            :return: `True` if the device supports the interface.
        """
        raise NotImplementedError


    @classmethod
    @abstractmethod
    def readDevinfo(cls, path: Filename, info=None) -> Union[None, bytearray, bytes]:
        """ Calculate the device's hash. Separated from `__hash__()` so it
            can be used by `getDevices()` to find known recorders.

            :param path: The device's filesystem path.
            :param info: The contents of the device's `DEVINFO` file, if
                previously loaded. For future caching optimization.
        """
        raise NotImplementedError


    @abstractmethod
    def readManifest(self) \
            -> Tuple[Union[None, bytearray, bytes], Union[None, bytearray, bytes], Union[None, bytearray, bytes]]:
        """ Read the device's manifest data. The data is a superset of the
            information returned by `getInfo()`.
        """
        raise NotImplementedError


    @abstractmethod
    def readUserCalibration(self) -> Union[None, bytearray, bytes]:
        """ Get the recorder's user-defined calibration data as a dictionary
            of parameters.
        """
        raise NotImplementedError


    @abstractmethod
    def writeUserCal(self,
                     caldata: Union[None, bytearray, bytes]):
        """ Write user calibration to the device.

            :param caldata: The raw binary of an EBML `<CalibrationList>`
                element..
        """
        raise NotImplementedError


# ===========================================================================
#
# ===========================================================================

class FileDeviceInfo(DeviceInfo):
    """
    A mechanism for retrieving device information from files (mostly
    firmware-generated) on the device. Its methods only read and write the raw
    binary; any parsing and/or encoding is done by the caller.
    """

    _INFO_FILE = os.path.join("SYSTEM", "DEV", "DEVINFO")


    def __init__(self, device: 'Recorder', **_kwargs):
        self.device = device
    

    @classmethod
    def hasInterface(cls, device: "Recorder") -> bool:
        """ Determine if a device supports this `DeviceInfo` type.

            :param device: The recorder to check.
            :return: `True` if the device supports the interface.
        """
        if device.isVirtual:
            return False

        return device.path and os.path.exists(device.infoFile)


    @classmethod
    def readDevinfo(cls,
                    path: Filename,
                    info: Union[None, bytearray, bytes] = None) -> Union[None, bytearray, bytes]:
        """ Retrieve a DEVINFO data. Calculate the device's hash. Separated from `__hash__()` so it
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

        return info


    def _readUserpage(self) \
            -> Tuple[Union[None, bytearray, bytes], Union[None, bytearray, bytes], Union[None, bytearray, bytes]]:
        """ Read the device's manifest data from the EFM32 'userpage'. The
            data is a superset of the information returned by `getInfo()`.
            Factory calibration and recorder properties are also read
            and cached, since one or both are in the userpage.
        """
        if self.device._manifest is not None:
            return self.device._manifest

        # Recombine all the 'user page' files
        data = bytearray()
        for i in range(4):
            filename = os.path.join(self.device.path, self.device._USERPAGE_FILE % i)
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
        if os.path.exists(self.device.recpropFile):
            with open(self.device.recpropFile, 'rb') as f:
                propData = f.read()
        else:
            # Zero offset means no property data (very old devices). For new
            # devices, a size of 1 also means no data (it's a null byte).
            propSize = 0 if (propOffset == 0 or propSize <= 1) else propSize
            propData = data[propOffset:propOffset + propSize]

        return manData, calData, propData


    def _readManifest(self) \
            -> Tuple[Union[None, bytearray, bytes], Union[None, bytearray, bytes], Union[None, bytearray, bytes]]:
        """ Read the device's manifest data from the 'MANIFEST' file. The
            data is a superset of the information returned by `getInfo()`.

            Factory calibration and recorder properties are also read and
            cached for backwards compatibility, since both are in the older
            devices' EFM32 'userpage'.
        """
        manFile = os.path.join(self.device.path, self.device._MANIFEST_FILE)
        calFile = os.path.join(self.device.path, self.device._SYSCAL_FILE)

        manData = calData = propData = None

        try:
            with open(manFile, 'rb') as f:
                manData = f.read()
        except (FileNotFoundError, AttributeError) as err:
            logger.debug(f"Possibly-allowed exception when reading {manFile}: {err!r}")

        try:
            with open(calFile, 'rb') as f:
                calData = f.read()
        except (FileNotFoundError, AttributeError) as err:
            logger.debug(f"Possibly-allowed exception when reading {calFile}: {err!r}")

        try:
            # _propData is read and cached here but parsed in `getSensors()`.
            # Old EFM32 recorders stored this w/ the manifest in the USERPAGE.
            with open(self.device.recpropFile, 'rb') as f:
                propData = f.read()
        except (FileNotFoundError, AttributeError) as err:
            logger.debug("Possibly-allowed exception when reading "
                         f"{self.device.recpropFile}: {err!r}")

        return manData, calData, propData


    def readManifest(self) \
            -> Tuple[Union[None, bytearray, bytes], Union[None, bytearray, bytes], Union[None, bytearray, bytes]]:
        """ Read the device's manifest data. The data is a superset of the
            information returned by `getInfo()`.
        """
        if os.path.exists(os.path.join(self.device.path, self.device._USERPAGE_FILE % 0)):
            return  self._readUserpage()
        elif os.path.exists(os.path.join(self.device.path, self.device._MANIFEST_FILE)):
            return self._readManifest()

        return None, None, None


    def readUserCalibration(self) -> Union[None, bytearray, bytes]:
        """ Get the recorder's user-defined calibration data as a dictionary
            of parameters.
        """
        if not os.path.isfile(self.device.userCalFile):
            return None

        with open(self.device.userCalFile, 'rb') as f:
            return f.read()


    def writeUserCal(self,
                     caldata: Union[None, bytearray, bytes]):
        """ Write user calibration to the device.

            :param caldata: The raw binary of an EBML `<CalibrationList>`
                element..
        """
        if caldata:
            try:
                util.makeBackup(self.device.userCalFile)
                with open(self.device.userCalFile, 'wb') as f:
                    f.write(caldata)
            except Exception:
                util.restoreBackup(self.device.userCalFile)
                raise


# ===========================================================================
#
# ===========================================================================

class SerialDeviceInfo(DeviceInfo):
    """
    A mechanism for retrieving device information from a remote device connected
    via a serial command interface. Its methods only read and write the raw
    binary; any parsing and/or encoding is done by the caller.
    """

    def __init__(self, device: 'Recorder', **_kwargs):
        self.device = device


    @classmethod
    def hasInterface(cls, device: "Recorder") -> bool:
        """ Determine if a device supports this `DeviceInfo` type.

            :param device: The recorder to check.
            :return: `True` if the device supports the interface.
        """
        if device.isVirtual or FileDeviceInfo.hasInterface(device):
            return False

        # return isinstance(device.command, SerialCommandInterface)
        return SerialCommandInterface.hasInterface(device)


    @classmethod
    def readDevinfo(cls,
                    path: Union[Filename, "Recorder"],
                    info: Optional[bytes] = None) -> Optional[bytes]:
        """ Retrieve a DEVINFO data.

            :param path: The device's filesystem path.
            :param info: The contents of the device's `DEVINFO` file, if
                previously loaded. For future caching optimization.
        """
        if isinstance(info, bytearray):
            info = bytes(info)
        if isinstance(getattr(path, 'command', None), SerialCommandInterface):
            return info or path.command._getInfo(0)
        return info


    def readManifest(self) \
            -> Tuple[Optional[bytes], Optional[bytes], Optional[bytes]]:
        """ Read the device's manifest data from the 'MANIFEST' file. The
            data is a superset of the information returned by `getInfo()`.

            Factory calibration and recorder properties are also read and
            cached for backwards compatibility, since both are in the older
            devices' EFM32 'userpage'.
        """
        manData = self.device.command._getInfo(3) or None
        calData = self.device.command._getInfo(4) or None
        propData = self.device.command._getInfo(1) or None

        return manData, calData, propData


    def readUserCalibration(self) -> Union[None, bytearray, bytes]:
        """ Get the recorder's user-defined calibration data as a dictionary
            of parameters.
        """
        self.device.command.setLockID()
        try:
            return self.device.command._getInfo(6, lock=True) or None
        finally:
            self.device.command.clearLockID()


    def writeUserCal(self,
                     caldata: Union[None, bytearray, bytes]):
        """ Write user calibration to the device.

            :param caldata: The raw binary of an EBML `<CalibrationList>`
                element..
        """
        if not self.device.available:
            raise UnsupportedFeature('Cannot write calibration over serial')

        return FileDeviceInfo.writeUserCal(self, caldata)


# ===========================================================================
#
# ===========================================================================

class MQTTDeviceInfo(SerialDeviceInfo):
    """
    A mechanism for retrieving device information from a remote device connected
    via MQTT. Its methods only read and write the raw binary; any parsing and/or
    encoding is done by the caller.
    """

    @classmethod
    def hasInterface(cls, device: "Recorder") -> bool:
        """ Determine if a device supports this `DeviceInfo` type.

            Note: it's likely that this interface will be instantiated
            by the mechanism that instantiates MQTT devices, so this
            won't be used.

            :param device: The recorder to check.
            :return: `True` if the device supports the interface.
        """
        if device.isVirtual:
            return False

        # TODO: Better mechanism for identifying MQTT devices?
        return device.path and device.path.lower().startswith(('mqtt', 'remote'))


    def writeUserCal(self,
                     caldata: Union[None, bytearray, bytes]):
        """ Write user calibration to the device.

            :param caldata: The raw binary of an EBML `<CalibrationList>`
                element..
        """
        caldata = caldata or b''

        self.device.command.setLockID()
        try:
            self.device.command._setInfo(6, caldata)
        finally:
            self.device.command.clearLockID()


# ===========================================================================
#
# ===========================================================================

#: A list of all `DeviceInfo` types, used when finding a device's  interface.
#  New interface types defined elsewhere should append/insert themselves into
#  this list.
INTERFACES = [FileDeviceInfo,
              SerialDeviceInfo,
              MQTTDeviceInfo]
