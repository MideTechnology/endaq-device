"""
Configuration interface tests.
"""

import os.path
import shutil
import pytest

import endaq.device
from endaq.device import getRecorder
from endaq.device import config, ui_defaults
from endaq.device.exceptions import ConfigError

from endaq.device.util import makeBackup

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


@pytest.mark.parametrize("path", RECORDER_ROOTS)
def test_temp(path, dev_copy_dir):
    """ Sanity check that temp copies of devices work.
    """
    endaq.device.RECORDERS.clear()
    dev = getRecorder(dev_copy_dir / path, strict=False)
    assert dev


@pytest.mark.parametrize("path", RECORDER_ROOTS)
def test_config_enable(path, dev_copy_dir):
    """ Test setting, writing, and reading channel enable. These items can
        be handled differently internally, so several channels are tested.
    """
    dev = getRecorder(dev_copy_dir / path, strict=False)

    # Remove existing config.cfg files (if any)
    makeBackup(dev.configFile)
    if os.path.exists(dev.configFile):
        os.remove(dev.configFile)

    # This will instantiate the ConfigInterface
    config = dev.config
    assert config

    # Test channels 8 and 59. These have 3 or more subchannels which can
    # be enabled/disabled individually. Most fake recorders have these.
    for chId in (8, 59):
        if chId not in dev.channels:
            continue

        dev.config.enableChannel(dev.channels[chId][0], False)
        dev.config.enableChannel(dev.channels[chId][1], True)
        dev.config.enableChannel(dev.channels[chId][2], False)

        # Verify these subchannels can only be enabled individually
        with pytest.raises(ConfigError):
            dev.config.enableChannel(dev.channels[chId], True)

        assert dev.config.isEnabled(dev.channels[chId][0]) is False
        assert dev.config.isEnabled(dev.channels[chId][1]) is True
        assert dev.config.isEnabled(dev.channels[chId][2]) is False

    # Test channel 80. It as 3 subchannels, but they cannot be individually
    # enabled/disabled. '*D40' recorders have this channel.
    if 80 in dev.channels:
        dev.config.enableChannel(dev.channels[80], False)
        assert dev.config.isEnabled(dev.channels[80]) is False

        # Verify only the channel as a whole can be enabled
        with pytest.raises(ConfigError):
            dev.config.enableChannel(dev.channels[80][0], True)

    # Save config
    dev.config.applyConfig()

    # Remove the old ConfigInterface and make a new one, ensuring all
    # config values are being read from the config file.
    dev.config = None
    assert dev.config is not config

    for chId in (8, 59):
        if chId not in dev.channels:
            continue

        assert dev.config.isEnabled(dev.channels[chId][0]) is False
        assert dev.config.isEnabled(dev.channels[chId][1]) is True
        assert dev.config.isEnabled(dev.channels[chId][2]) is False

    if 80 in dev.channels:
        assert dev.config.isEnabled(dev.channels[80]) is False
