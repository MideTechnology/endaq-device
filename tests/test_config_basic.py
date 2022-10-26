"""
Configuration interface tests.
"""

import os.path
import pytest

import endaq.device
from endaq.device import getRecorder
from endaq.device import config, ui_defaults

from .fake_recorders import RECORDER_PATHS

# Clear any cached devices, just to be safe
endaq.device.RECORDERS.clear()

# Create parameters, mainly to provide an ID, making the results readable
DEVICES = [pytest.param(getRecorder(path, strict=False), id=os.path.basename(path)) for path in RECORDER_PATHS]


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
