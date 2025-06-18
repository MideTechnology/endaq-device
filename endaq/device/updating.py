"""
Utility functions for validating enDAQ update packages: firmware
``update.pkg`` and manifest/calibration ``userpage.bin`` files.
"""

import io
import pathlib
import struct
from typing import ByteString, Optional, Tuple, Union
from ebmlite import loadSchema, Element

from endaq.device.exceptions import UnsupportedFeature, ValidationError

import logging
logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from endaq.device.base import Recorder


# ==============================================================================
#
# ==============================================================================

def parseUserpage(data: Union[str, pathlib.Path, ByteString]
                  ) -> Tuple[Element, Element, Optional[Element]]:
    """
    Parse the contents of a ``userpage.bin`` update file into dictionaries:
    manifest, factory calibration, and (optional) recording properties.
    The latter is only present in updates for old firmware.

    :param data: The name of a userpage file, or a byte string containing the
        contents of a userpage file.
    :return: A three-item tuple containing parsed EBML Elements for the
        manifest and calibration, and an EBML Element for the recorder
        properties (or `None` if the file does not contain recorder
        properties).
    """
    if isinstance(data, (str, pathlib.Path)):
        with open(data, 'rb') as f:
            data = f.read()

    (manOffset, manSize,
     calOffset, calSize,
     propOffset, propSize) = struct.unpack_from("<HHHHHH", data)

    manData = data[manOffset:manOffset + manSize]
    calData = data[calOffset:calOffset + calSize]

    if propOffset > 0 and propSize > 1:
        propData = data[propOffset:propOffset + propSize]
    else:
        propData = None

    manSchema = loadSchema('mide_manifest.xml')
    ideSchema = loadSchema('mide_ide.xml')

    manData = manSchema.loads(manData)[0]
    calData = ideSchema.loads(calData)[0]
    if propData is not None:
        propData = ideSchema.loads(propData)[0]

    return manData, calData, propData


# ==============================================================================
#
# ==============================================================================

def validatePackage(device: "Recorder",
                    package: Union[str, pathlib.Path, io.IOBase]) -> bool:
    """
    Check that a firmware update package is valid and compatible with a
    given device. Failure will raise an exception (likely, but not
    exclusively, one listed here).

    :raises UnsupportedFeature: if the device cannot be updated.
    :raises ValueError: if the update package is invalid (unreadable or
        missing critical information).
    :raises ValidationError: if the userpage update is not compatible with
        the specific device.

    :param device: The :class:`Recorder` to update.
    :param package: The name of an update package file, or a byte string
        containing the binary contents of an update package.
    """
    if device.isVirtual:
        raise UnsupportedFeature('Virtual devices cannot be updated')
    elif not device.canCopyFirmware:
        raise UnsupportedFeature('The device cannot be updated via software')
    elif not device.mcuType:
        ValueError("Could not determine device's MCU type")

    with loadSchema('flash_package.xml').load(package) as doc:
        if doc[0].name != 'UpdatePkg':
            raise ValueError('Could not read information from the update package')
        info = doc[0].dump()

    if info.get('TargetProcessor') != device.mcuType:
        raise ValidationError("The update package does not support the device's processor")
    if info.get('MinHWRev', 0) > device.hardwareVersionInt:
        raise ValidationError("The update package does not support the device's hardware version")
    if info.get('MinFWRev', 0) > device.firmwareVersion:
        raise ValidationError("The update package does not support the device's firmware version")

    if device.hasWifi and 'NcpUpdate' in info:
        _, _sep, ncp = device.hasWifi.partition('_')
        if ncp not in info.get('NcpUpdate').get('NcpType', ''):
            raise ValidationError("The update package does not support the device's Wi-Fi hardware")

    pkgEncrypted = info.get('KeySlot', -1) > 0
    devEncrypted = device.getInfo('KeyRev', 0) > 0
    if not devEncrypted and pkgEncrypted:
        raise ValidationError("The device requires an unencrypted update package")

    return True


def validateUserpage(device: "Recorder",
                     userpage: Union[str, pathlib.Path, io.IOBase],
                     strict: bool = True):
    """
    Check that a 'userpage' update (device manifest and calibration) is
    valid and compatible with a given device. Failure will raise an
    exception (likely, but not exclusively, one listed here).

    :raises UnsupportedFeature: if the device cannot be updated.
    :raises ValueError: if the userpage update is invalid (unreadable or
        missing critical information).
    :raises ValidationError: if the userpage update is not intended for
        the specific device.

    :param device: The :class:`Recorder` to update.
    :param userpage: The name of a userpage update file, or a byte string
        containing the contents of a userpage update file.
    :param strict: If `True`, the serial number in the update data must match
        the device's. If `False`, only an update validity check is performed.
    """
    if device.isVirtual:
        raise UnsupportedFeature('Virtual devices cannot be updated')
    elif not device.canCopyFirmware:
        raise UnsupportedFeature('The device cannot be updated via software')

    man, cal, _ = parseUserpage(userpage)
    if man.value[0].name != 'SystemInfo':
        raise ValueError('Could not read information from the update data')

    sn = man.value[0].dump().get('SerialNumber')
    if not sn:
        raise ValueError('Manifest update did not contain a valid serial number')

    if not strict:
        return

    if sn != device.serialInt:
        raise ValidationError(f'Serial number in manifest update {sn!r} '
                              f'did not match device {device.serialInt}')


def validateFirmware(device: "Recorder",
                     data: Union[str, pathlib.Path, io.IOBase]) -> bool:
    """
    Perform basic validation of an unencrypted firmware ``.bin`` file to
    confirm it is compatible with the given device. Only devices without
    encryption can use ``.bin`` firmware updates.

    :raises UnsupportedFeature: if the device cannot be updated.
    :raises ValueError: if the userpage update is invalid (unreadable or
        missing critical information).
    :raises ValidationError: if the userpage update is not intended for
        the specific device.

    :param device: The :class:`Recorder` to update.
    :param data: The name of a userpage file, or a byte string containing the
        contents of a userpage file.
    """
    if device.isVirtual:
        raise UnsupportedFeature('Virtual devices cannot be updated')
    elif not device.canCopyFirmware:
        raise UnsupportedFeature('The device cannot be updated via software')
    elif device.getInfo('KeyRev', -1) > 0:
        UnsupportedFeature('Devices with encryption require encrypted firmware')
    elif not device.mcuType:
        ValueError("Could not determine device's MCU type")

    if isinstance(data, (str, pathlib.Path)):
        with open(data, 'rb') as f:
            data = f.read()

    # This is a fairly primitive set of checks: they just look for certain
    # cleartext strings in the binary.

    if device.mcuType == 'EFM32GG330':
        # Old EFM32 series 0 device FW slightly different
        if b'EFM32' not in data:
            raise ValidationError('The firmware does not appear support this device')

    elif b'Mide Technology' not in data:
        raise ValueError('The file does not appear to be an enDAQ firmware update')
    elif device.mcuType and bytes(device.mcuType, 'ascii') not in data:
        raise ValidationError('The firmware does not appear support this device')

    return True
