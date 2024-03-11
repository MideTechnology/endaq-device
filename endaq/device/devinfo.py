"""
'Strategy' classes for reading device information over different media
(e.g., file-based or through the command interface). These are similar to
`CommandInterface` and `ConfigInterface`, except that they are not accessed
directly.
"""
from abc import ABC
import logging
import os.path
import struct
from typing import ByteString, Optional, Tuple, TYPE_CHECKING

from .exceptions import *
from .types import Drive, Filename

logger = logging.getLogger('endaq.device')

if TYPE_CHECKING:
    from .base import Recorder


# ===============================================================================
#
# ===============================================================================

class DeviceInfo(ABC):
    """ An abstract mechanism for retrieving device information. Its methods
        only read and write the raw binary.
    """

    def _getInfo(self, path=None) -> Optional[ByteString]:
        """ Read a recorder's device information """
    ...


    @classmethod
    def readDevinfo(cls, path: Filename, info=None) -> Optional[ByteString]:
        """ Calculate the device's hash. Separated from `__hash__()` so it
            can be used by `getDevices()` to find known recorders.

            :param path: The device's filesystem path.
            :param info: The contents of the device's `DEVINFO` file, if
                previously loaded. For future caching optimization.
        """
        ...


    def readManifest(self) \
            -> Tuple[Optional[ByteString], Optional[ByteString], Optional[ByteString]]:
        """ Read the device's manifest data. The data is a superset of the
            information returned by `getInfo()`.
        """
        ...


    def readUserCalibration(self) -> Optional[ByteString]:
        """ Get the recorder's user-defined calibration data as a dictionary
            of parameters.
        """
        ...


    def writeUserCal(self,
                     caldata: ByteString):
        """ Write user calibration to the device.

            :param caldata: The raw binary of an EBML `<CalibrationList>`
                element..
        """
        ...


# ===============================================================================
#
# ===============================================================================

class FileDeviceInfo(DeviceInfo):
    """
    A mechanism for retrieving device information from files (mostly
    firmware-generated) on the device.
    """

    _INFO_FILE = os.path.join("SYSTEM", "DEV", "DEVINFO")


    def __init__(self, device: 'Recorder', **_kwargs):
        self.device = device
    
    
    @classmethod
    def readDevinfo(cls, path: Filename, info=None) -> Optional[ByteString]:
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

        return info


    def _getInfo(self, path=None) -> Optional[ByteString]:
        """ Read a recorder's device information """
        if path:
            infoFile = os.path.join(path, self.device._INFO_FILE)
        else:
            infoFile = self.device.infoFile
        if not os.path.isfile(infoFile):
            return None
        with open(infoFile, 'rb') as f:
            return f.read()

    
    def _readUserpage(self) \
            -> Tuple[Optional[ByteString], Optional[ByteString], Optional[ByteString]]:
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
            -> Tuple[Optional[ByteString], Optional[ByteString], Optional[ByteString]]:
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
            -> Tuple[Optional[ByteString], Optional[ByteString], Optional[ByteString]]:
        """ Read the device's manifest data. The data is a superset of the
            information returned by `getInfo()`.
        """
        if os.path.exists(os.path.join(self.device.path, self.device._USERPAGE_FILE % 0)):
            return  self._readUserpage()
        elif os.path.exists(os.path.join(self.device.path, self.device._MANIFEST_FILE)):
            return self._readManifest()

        return None, None, None


    def readUserCalibration(self) -> Optional[ByteString]:
        """ Get the recorder's user-defined calibration data as a dictionary
            of parameters.
        """
        if not os.path.isfile(self.device.userCalFile):
            return None

        with open(self.device.userCalFile, 'rb') as f:
            return f.read()


    def writeUserCal(self,
                     caldata: ByteString):
        """ Write user calibration to the device.

            :param caldata: The raw binary of an EBML `<CalibrationList>`
                element..
        """
        if caldata:
            with open(self.device.userCalFile, 'wb') as f:
                f.write(caldata)

