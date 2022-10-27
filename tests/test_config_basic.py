"""
Configuration interface tests.
"""

import os.path
import shutil
import pytest

import endaq.device
from endaq.device import getRecorder
from endaq.device import config, ui_defaults

from .fake_recorders import RECORDER_PATHS

# Clear any cached devices, just to be safe
endaq.device.RECORDERS.clear()

# Create parameters, mainly to provide an ID, making the results readable
DEVICES = [pytest.param(getRecorder(path, strict=False), id=os.path.basename(path))
           for path in RECORDER_PATHS]


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


@pytest.mark.parametrize("dev", DEVICES)
def test_config_basics(dev):
    """ Initial 'sanity test' to verify `ConfigInterface` instances are
        being instantiated.
    """
    assert isinstance(dev.config, config.ConfigInterface)


@pytest.mark.parametrize("dev", DEVICES)
def test_configui_defaults(dev):
    """ Confirm there is default ConfigUI data for each fake recorder.
    """
    assert ui_defaults.getDefaultConfigUI(dev) is not None


@pytest.mark.parametrize("path", [os.path.basename(p) for p in RECORDER_PATHS])
def test_temp(path, dev_copy_dir):
    """ Sanity check that temp copies of devices work.
    """
    endaq.device.RECORDERS.clear()
    dev = getRecorder(dev_copy_dir / path, strict=False)
    assert dev

