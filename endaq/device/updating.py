"""
Utility functions for reading and validating enDAQ update packages:
firmware ``update.pkg`` and ``firmware.bin`` files, and
manifest/calibration ``userpage.bin`` files.
"""

import io
import pathlib
import struct
from typing import Any, ByteString, Dict, Optional, Tuple, Union
from ebmlite import loadSchema

from .exceptions import DeviceError, UnsupportedFeature, ValidationError
from . import util

import logging
logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from endaq.device.base import Recorder


# ==============================================================================
#
# ==============================================================================

def parsePackage(package: Union[str, pathlib.Path, ByteString]) -> Dict[str, Any]:
    """
    Parse the package info from a ``.pkg`` firmware update file.

    :raises ValueError: if the header of ``package`` can't be parsed (e.g.,
        damaged or the file is not an update package).

    :param package: The name of an update package file, or a byte string
        containing the binary contents of an update package.
    :return: A dictionary of parsed package header information.
    """
    try:
        with loadSchema('flash_package.xml').load(package) as doc:
            if doc[0].name != 'UpdatePkg':
                raise ValueError('Could not read information from the update package')
            return doc[0].dump()
    except (IndexError, OSError, TypeError, ValueError, struct.error) as err:
        logging.debug(f'parsePackage failed: {err!r}')
        if (isinstance(err, OSError)
                and not (err.errno is None and 'Invalid length' in str(err))):
            # ebmlite currently raises IOError/OSError when something won't
            # parse; this may/should be changing in the future.
            raise
        raise ValueError('Could not parse information from the update package')


def isPackage(package):
    """
    Check that a ``.pkg`` file is actually a readable firmware update package.

    :param package: The name of a update package file, or a byte string
        containing the contents of a userpage file.
    """
    try:
        _ = parsePackage(package)
        return True
    except ValueError:
        return False


def validatePackage(device: "Recorder",
                    package: Union[str, pathlib.Path, io.IOBase]) -> bool:
    """
    Check that a firmware update package is valid and compatible with a
    given device. Failure will raise an exception (likely, but not
    exclusively, one listed here).

    :raises UnsupportedFeature: if the device cannot be updated. If catching
        this, do it before catching `DeviceError`.
    :raises ValidationError: if the update package is not intended for
        the specific device. If catching this, do it before `ValueError`.
    :raises ValueError: if the update package is invalid (unreadable or
        missing critical information).
    :raises DeviceError: if the device has a problem that prohibits updating.

    :param device: The :class:`Recorder` to update.
    :param package: The name of an update package file, or a byte string
        containing the binary contents of an update package.
    """
    if device.isVirtual:
        raise UnsupportedFeature('Virtual devices cannot be updated')
    elif not device.canCopyFirmware:
        raise UnsupportedFeature('The device cannot be updated via software')
    elif not device.mcuType:
        raise DeviceError("Could not determine device's MCU type")

    info = parsePackage(package)

    mcu = info.get('TargetProcessor', 'EFM32GG11B820')
    hw = info.get('MinHWRev', 0)
    fw = info.get('MinFWRev', 0)

    if mcu != device.mcuType:
        raise ValidationError("The update package does not support the device's processor "
                              f"(device is {device.mcuType}, update requires {mcu})")
    if hw > device.hardwareVersionInt:
        raise ValidationError("The update package does not support the device's hardware version "
                              f"(device is {device.hardwareVersion}, "
                              f"update requires at least {util.formatHwRev(hw)})")
    if fw > device.firmwareVersion:
        raise ValidationError("The update package does not support the device's firmware version "
                              f"(device has {util.formatFwRev(device.firmware)},"
                              f" update requires at least {util.formatFwRev(fw)})")

    if device.hasWifi and 'NcpUpdate' in info:
        _, _sep, ncp = device.hasWifi.partition('_')
        if ncp not in info.get('NcpUpdate').get('NcpType', ''):
            # HACK: This test may be brittle
            raise ValidationError("The update package does not support the device's Wi-Fi hardware")

    pkgEncrypted = info.get('KeySlot', -1) > 0
    devEncrypted = device.getInfo('KeyRev', 0) > 0
    if not devEncrypted and pkgEncrypted:
        raise ValidationError("The device requires an unencrypted update package")

    return True


# ==============================================================================
#
# ==============================================================================

def parseUserpage(data: Union[str, pathlib.Path, ByteString]
                  ) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[Dict]]:
    """
    Parse the contents of a ``userpage.bin`` update file into dictionaries:
    manifest, factory calibration, and (optional) recording properties.
    The latter is only present in updates for old firmware.

    :raises ValueError: if the file cannot be parsed (e.g., damaged or not a
        userpage update).

    :param data: The name of a userpage file, or a byte string containing the
        contents of a userpage file.
    :return: A three-item tuple containing dictionaries of manifest and
        calibration data, and a dictionary of recorder properties (or `None`
        if the file does not contain recorder properties).
    """
    if isinstance(data, (str, pathlib.Path)):
        with open(data, 'rb') as f:
            data = f.read()

    try:
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
            propData = ideSchema.loads(propData)[0].dump()

        if (len(manData) == 0 or len(calData) == 0
                or manData.name != 'DeviceManifest'
                or calData.name != 'CalibrationList'):
            raise ValueError('Userpage update file could not be parsed')

        return manData.dump(), calData.dump(), propData

    except (IndexError, OSError, TypeError, ValueError, struct.error) as err:
        logging.debug(f'parseUserpage failed: {err!r}')
        if (isinstance(err, OSError)
                and not (err.errno is None and 'Invalid length' in str(err))):
            # ebmlite currently raises IOError/OSError when something won't
            # parse; this may/should be changing in the future.
            raise
        raise ValueError('Userpage update file could not be parsed')


def isUserpage(data: Union[str, pathlib.Path, ByteString]) -> bool:
    """
    Check that a ``.bin`` file is actually a readable 'userpage' update and
    not something else (i.e., an unencrypted firmware update).

    :param data: The name of a userpage file, or a byte string containing the
        contents of a userpage file.
    """
    try:
        _ = parseUserpage(data)
        return True
    except ValueError:
        return False


def validateUserpage(device: "Recorder",
                     userpage: Union[str, pathlib.Path, io.IOBase],
                     strict: bool = True) -> bool:
    """
    Check that a 'userpage' update (device manifest and calibration) is
    valid and compatible with a given device. Failure will raise an
    exception (likely, but not exclusively, one listed here).

    :raises UnsupportedFeature: if the device cannot be updated. If catching
        this, do it before catching `DeviceError`.
    :raises ValidationError: if the userpage update is not intended for
        the specific device. If catching this, do it before `ValueError`.
    :raises ValueError: if the userpage update is invalid (unreadable or
        missing critical information).
    :raises DeviceError: if the device has a problem that prohibits updating.

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
    elif not device.serial and strict:
        raise DeviceError("Could not determine device's serial number")

    man, cal, _ = parseUserpage(userpage)

    try:
        sn = man['SystemInfo']['SerialNumber']
        if not sn:
            raise ValueError('Manifest update did not contain a valid serial number')
    except KeyError:
        raise ValueError('Manifest update did not contain a serial number')

    if strict and sn != device.serialInt:
        raise ValidationError(f'Serial number in manifest update did not '
                              f'match device ({sn!r} != {device.serialInt})')

    return True


# ==============================================================================
#
# ==============================================================================

def parseFirmware(data: Union[str, pathlib.Path, ByteString]) -> bytes:
    """
    Parse the contents of a ``.bin`` unencrypted firmware update file.
    Basic validation that the input is a firmware update is performed.

    :raises ValueError: if the file cannot be parsed (e.g., damaged or not a
        firmware update).

    :param data: The name of a firmware file, or a byte string containing the
        contents of a firmware file.
    :return: The contents of the firmware file. If the function was called
        with the contents of a file, it is returned verbatim if it passes
        basic validation.
    """
    if isinstance(data, (str, pathlib.Path)):
        with open(data, 'rb') as f:
            data = f.read()

    # Most basic test: check it isn't another kind of update. Those tests
    # are more stringent and are unlikely to give a false positive that
    # would pass this function's tests.
    if isUserpage(data):
        raise ValueError('File is a userpage update, not firmware')
    if isPackage(data):
        raise ValueError('File is a firmware package, not an unencrypted firmware binary')

    # This is a fairly primitive set of checks: they just look for certain
    # cleartext strings in the binary.

    # Copyright string text. EFM32GG330 updates have string of characters
    # padded to 16b; others have a different one.
    company = (b'M\x00I\x00D\x00E\x00 \x00T\x00e\x00c\x00h\x00n\x00o\x00l\x00o\x00g\x00y',
               b'Mide Technology')

    # MCU type. These strings should appear somewhere in a valid update.
    mcus = (b'EFM32', b'STM32')

    if (not any(c in data for c in company)
            or not any(m in data for m in mcus)):
        raise ValueError('The file does not appear to be an enDAQ firmware update')

    return data


def isFirmware(data: Union[str, pathlib.Path, ByteString]) -> bool:
    """
    Check that a ``.bin`` file is actually a readable unencrypted firmware
    update and not something else (i.e., a 'userpage' update).

    :param data: The name of a firmware file, or a byte string containing the
        contents of a firmware file.
    """
    try:
        _ = parseFirmware(data)
        return True
    except ValueError:
        return False


def validateFirmware(device: "Recorder",
                     data: Union[str, pathlib.Path, io.IOBase]) -> bool:
    """
    Perform basic validation of an unencrypted firmware ``.bin`` file to
    confirm it is compatible with the given device. Only devices without
    encryption can use ``.bin`` firmware updates.

    :raises UnsupportedFeature: if the device cannot be updated. If catching
        this, do it before catching `DeviceError`.
    :raises ValidationError: if the firmware update is not intended for
        the specific device. If catching this, do it before `ValueError`.
    :raises ValueError: if the firmware update is invalid (unreadable or
        missing critical information).
    :raises DeviceError: if the device has a problem that prohibits updating.

    :param device: The :class:`Recorder` to update.
    :param data: The name of a userpage file, or a byte string containing the
        contents of a userpage file.
    """
    if device.isVirtual:
        raise UnsupportedFeature('Virtual devices cannot be updated')
    elif not device.canCopyFirmware:
        raise UnsupportedFeature('The device cannot be updated via software')
    elif device.getInfo('KeyRev', -1) > 0:
        raise ValidationError('Devices with encryption require a firmware .pkg file')
    elif not device.mcuType:
        raise DeviceError("Could not determine device's MCU type")

    data = parseFirmware(data)

    # This is a fairly primitive set of checks: they just look for certain
    # cleartext strings in the binary.
    if device.mcuType == 'EFM32GG330':
        # Old EFM32 series 0 device FW slightly different
        if b'Mide Technology' in data:
            raise ValueError('The file does not appear to support this device type')
        if b'EFM32' not in data:
            raise ValidationError("The firmware does not appear support this device type")
    elif device.mcuType and bytes(device.mcuType, 'ascii') not in data:
        raise ValidationError('The firmware does not appear support this device type')

    return True
