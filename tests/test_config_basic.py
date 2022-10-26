import pytest

import endaq.device
from endaq.device import config, ui_defaults

from .fake_recorders import RECORDER_PATHS

endaq.device.RECORDERS.clear()  # Clear any cached devices, just to be safe
DEVICES = [endaq.device.getRecorder(path, strict=False) for path in RECORDER_PATHS]


@pytest.mark.parametrize("dev", DEVICES)
def test_config_basics(dev):
    """ Initial 'sanity test' to verify `ConfigInterface` instances are
        being instantiated.
    """
    # dev = endaq.device.getRecorder(path, strict=False)
    assert isinstance(dev.config, config.ConfigInterface)


@pytest.mark.parametrize("dev", DEVICES)
def test_configui_defaults(dev):
    """ Confirm there is default ConfigUI data for each fake recorder.
    """
    assert ui_defaults.getDefaultConfigUI(dev) is not None
