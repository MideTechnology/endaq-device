"""
'Strategy' classes for reading device information over different media
(e.g., file-based or through the command interface). These are similar to
`CommandInterface` and `ConfigInterface`, except that they are not accessed
directly.
"""
import logging
import os.path
from pathlib import Path
import struct
from typing import Any, AnyStr, ByteString, Dict, List, Optional, Tuple, Union, Callable, TYPE_CHECKING

from ebmlite import loadSchema, Document
from idelib.dataset import Dataset, Channel, SubChannel, Sensor
from idelib import importer
from idelib.parsers import CalibrationListParser, RecordingPropertiesParser
from idelib.transforms import Transform

from .exceptions import *
from .types import Drive, Filename, Epoch

logger = logging.getLogger('endaq.device')

if TYPE_CHECKING:
    from .base import Recorder


class FileDeviceInfo:
    
    _INFO_FILE = os.path.join("SYSTEM", "DEV", "DEVINFO")


    def __init__(self, device: 'Recorder', **kwargs):
        self.device = device
    
    
    @classmethod
    def readDevinfo(cls, path: Filename, info=None) -> Union[None, ByteString]:
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


    def _getInfo(self, path=None):
        """ Read a recorder's device information """
        if path:
            infoFile = os.path.join(path, self.device._INFO_FILE)
        else:
            infoFile = self.device.infoFile
        if not os.path.isfile(infoFile):
            return None
        with open(infoFile, 'rb') as f:
            return f.read()


    
    def _readUserpage(self) -> Union[Dict[str, Any], None]:
        """ Read the device's manifest data from the EFM32 'userpage'. The
            data is a superset of the information returned by `getInfo()`.
            Factory calibration and recorder properties are also read
            and cached, since one or both are in the userpage.

            Note: This method sets `Recorder._propData`, `Recorder._manData`,
            `Recorder._calData`, `Recorder._manifest`, and
            `Recorder._calibration`.
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
                self.device._propData = f.read()
        else:
            # Zero offset means no property data (very old devices). For new
            # devices, a size of 1 also means no data (it's a null byte).
            propSize = 0 if (propOffset == 0 or propSize <= 1) else propSize
            self.device._propData = data[propOffset:propOffset + propSize]

        try:
            self.device._manData = loadSchema("mide_manifest.xml").loads(manData)
            self.device._manifest = self.device._manData.dump().get('DeviceManifest')

            self.device._calData = loadSchema("mide_ide.xml").loads(calData)
            self.device._calibration = self.device._calData.dump().get('CalibrationList')

        except (AttributeError, KeyError) as err:
            logger.debug("_readUserpage() raised a possibly-allowed exception: %r" % err)
            pass

        return self.device._manifest


    def _readManifest(self) -> Union[Dict[str, Any], None]:
        """ Read the device's manifest data from the 'MANIFEST' file. The
            data is a superset of the information returned by `getInfo()`.

            Factory calibration and recorder properties are also read and
            cached for backwards compatibility, since both are in the older
            devices' EFM32 'userpage'.

            Note: This method sets `Recorder._propData`, `Recorder._manData`,
            `Recorder._calData`, `Recorder._manifest`, and
            `Recorder._calibration`.

        """
        manFile = os.path.join(self.device.path, self.device._MANIFEST_FILE)
        calFile = os.path.join(self.device.path, self.device._SYSCAL_FILE)

        try:
            with open(manFile, 'rb') as f:
                self.device._manData = loadSchema("mide_manifest.xml").loads(f.read())
            self.device._manifest = self.device._manData.dump().get('DeviceManifest')
        except (FileNotFoundError, AttributeError, KeyError) as err:
            logger.debug(f"Possibly-allowed exception when reading {manFile}: {err!r}")

        try:
            with loadSchema("mide_ide.xml").load(calFile) as doc:
                self.device._calData = doc.schema.loads(doc.getRaw())
                self.device._calibration = self.device._calData[0].dump()
        except (FileNotFoundError, AttributeError, IndexError) as err:
            logger.debug(f"Possibly-allowed exception when reading {calFile}: {err!r}")

        try:
            # _propData is read and cached here but parsed in `getSensors()`.
            # Old EFM32 recorders stored this w/ the manifest in the USERPAGE.
            with open(self.device.recpropFile, 'rb') as f:
                self.device._propData = f.read()
        except (FileNotFoundError, AttributeError, KeyError) as err:
            logger.debug("Possibly-allowed exception when reading "
                         f"{self.device.recpropFile}: {err!r}")

        return self.device._manifest


    def getManifest(self) -> Union[Dict[str, Any], None]:
        """ Read the device's manifest data. The data is a superset of the
            information returned by `getInfo()`.
        """
        if os.path.exists(os.path.join(self.device.path, self.device._USERPAGE_FILE % 0)):
            self._readUserpage()
        elif os.path.exists(os.path.join(self.device.path, self.device._MANIFEST_FILE)):
            self._readManifest()

        return self.device._manifest



    def getUserCalibration(self) -> Optional[Document]:
        """ Get the recorder's user-defined calibration data as a dictionary
            of parameters.
        """
        if not os.path.isfile(self.device.userCalFile):
            return None

        with open(self.device.userCalFile, 'rb') as f:
            return loadSchema("mide_ide.xml").loads(f.read())


    def writeUserCal(self,
                     transforms: Union[List[Transform], Dict[int, Transform]]):
        """ Write user calibration to the device.

            :param transforms: A dictionary or list of `idelib.calibration`
                objects.
        """
        with open(self.device.userCalFile, 'wb') as f:
            f.write(self.device.generateCalEbml(transforms))


