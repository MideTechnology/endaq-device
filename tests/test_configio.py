"""
Test configuration import/export.
"""

import os.path
import shutil
import pytest

from endaq.device import getRecorder
import endaq.device.configio

from .fake_recorders import RECORDER_PATHS

# Clear any cached devices, just to be safe
endaq.device.RECORDERS.clear()

# Create parameters, mainly to provide an ID, making the results readable
DEVICES = [pytest.param(getRecorder(path, strict=False), id=os.path.basename(path))
           for path in RECORDER_PATHS]

RECORDER_ROOTS = [os.path.basename(p) for p in RECORDER_PATHS]


@pytest.fixture(scope="session")
def dev_copy_dir(tmpdir_factory):
    """ Fixture to make copies of the fake recorders, for tests that affect
        files on the device (configuration, commands, etc.).
    """
    workdir = tmpdir_factory.mktemp("recorders")
    for src in RECORDER_PATHS:
        dst = workdir / os.path.basename(src)
        shutil.copytree(src, dst)
    return workdir


# ============================================================================
#
# ============================================================================

@pytest.mark.parametrize("path", RECORDER_ROOTS)
def test_basic_export_import(path, dev_copy_dir):
    """ Test basic configuration import/export.
    """
    dev = getRecorder(dev_copy_dir / path, strict=False)
    exportName = dev_copy_dir / f'{dev.partNumber}.xcg'

    originalName = dev.config.name
    # config = dev.config.getConfigValues(defaults=True, none=True)
    endaq.device.configio.exportConfig(dev, exportName)
    assert os.path.exists(exportName)

    foo = endaq.device.configio.deviceFromExport(exportName)
    assert foo.partNumber == dev.partNumber

    dev.config.name = "Changed name"
    assert dev.name != originalName

    endaq.device.configio.importConfig(dev, exportName)
    assert dev.name == originalName

    # TODO: Test more actual config values
