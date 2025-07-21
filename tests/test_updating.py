"""
Test update file validation, firmware and userpage.
"""

import os.path
import pytest

import endaq.device
import endaq.device.util

import endaq.device.updating
from endaq.device.updating import ValidationError, UnsupportedFeature

from .fake_recorders import RECORDER_PATHS
from . import updates

# Create parameters, mainly to provide an ID, making the results readable
DEVICES = [pytest.param(endaq.device.getRecorder(path, strict=False), id=os.path.basename(path))
           for path in RECORDER_PATHS]

UPDATEABLE_DEVICES = [param for param in DEVICES if param[0][0].canCopyFirmware]
UNUPDATEABLE_DEVICES = [param for param in DEVICES if not param[0][0].canCopyFirmware]

ENCRYPTED_DEVICES = [param for param in UPDATEABLE_DEVICES if param[0][0].getInfo('KeyRev')]
UNENCRYPTED_DEVICES = [param for param in UPDATEABLE_DEVICES if not param[0][0].getInfo('KeyRev')]


# ==============================================================================
# Update identification tests (positive/negative)
# ==============================================================================

@pytest.mark.parametrize("up", updates.USERPAGES)
def test_isUserpage(up):
    """ Basic test that userpage update files can be identified.
    """
    assert endaq.device.updating.isUserpage(up)


@pytest.mark.parametrize("up", updates.FIRMWARE_ALL)
def test_isUserpage_fail(up):
    """ Basic test that non-userpage update files can be identified.
    """
    assert not endaq.device.updating.isUserpage(up)


@pytest.mark.parametrize("fw", updates.FIRMWARE_PKG)
def test_isPackage(fw):
    """ Basic test that userpage update files can be identified.
    """
    assert endaq.device.updating.isPackage(fw)


@pytest.mark.parametrize("fw", updates.FIRMWARE_BIN)
def test_isPackage_fail(fw):
    """ Basic test that non-userpage update files can be identified.
    """
    assert not endaq.device.updating.isPackage(fw)


@pytest.mark.parametrize("fw", updates.FIRMWARE_BIN)
def test_isFirmware(fw):
    """ Basic test that unencrypted firmware update files can be identified.
    """
    assert endaq.device.updating.isFirmware(fw)


@pytest.mark.parametrize("fw", updates.USERPAGES)
def test_isFirmware_fail(fw):
    """ Basic test that non-firmware ``.bin`` update files can be identified.
    """
    assert not endaq.device.updating.isFirmware(fw)


# ==============================================================================
# Device validation tests
# ==============================================================================

@pytest.mark.parametrize("dev", UPDATEABLE_DEVICES)
def test_validateUserpage_basic(dev):
    """ Check that only the userpage for the specific device validates.
    """
    for up in updates.USERPAGES:
        try:
            endaq.device.updating.validateUserpage(dev, up)
            assert dev.serial in up
        except ValidationError:
            pass


@pytest.mark.parametrize("dev", UNUPDATEABLE_DEVICES)
def test_validateUserpage_unupdateable(dev):
    """ Test that old devices that can't update FW via files fail with an
        `UnsupportedFeature` exception.
    """
    for up in updates.USERPAGES:
        with pytest.raises(UnsupportedFeature):
            endaq.device.updating.validateUserpage(dev, up)


@pytest.mark.parametrize("dev", UNENCRYPTED_DEVICES)
def test_validatePackage_devicetype(dev):
    """ Verify packages for the wrong MCU fail validation.
    """
    for fw in updates.FIRMWARE_PKG:
        if dev.mcuType in fw:
            continue

        with pytest.raises(ValidationError):
            endaq.device.updating.validatePackage(dev, fw)


@pytest.mark.parametrize("dev", UNENCRYPTED_DEVICES)
def test_validatePackage_unencrypted(dev):
    """ Test packages vs. devices without encryption. Only unencrypted
        packages should pass.
    """
    for fw in updates.FIRMWARE_PKG_UNENCRYPTED:
        if dev.mcuType not in fw:
            continue
        endaq.device.updating.validatePackage(dev, fw)

    for fw in updates.FIRMWARE_PKG_ENCRYPTED:
        with pytest.raises(ValidationError):
            endaq.device.updating.validatePackage(dev, fw)

    for fw in updates.FIRMWARE_BIN:
        if dev.mcuType not in fw:
            continue
        endaq.device.updating.validateFirmware(dev, fw)


@pytest.mark.parametrize("dev", ENCRYPTED_DEVICES)
def test_validatePackage_encrypted(dev):
    """ Test packages vs. devices with encryption. Both encrypted
        and unencrypted packages should pass.
    """
    for fw in updates.FIRMWARE_PKG:
        if dev.mcuType not in fw:
            continue
        endaq.device.updating.validatePackage(dev, fw)

    for fw in updates.FIRMWARE_BIN:
        with pytest.raises(ValidationError):
            endaq.device.updating.validateFirmware(dev, fw)
