import pytest

import endaq.device
from endaq.device import ui_defaults

from .fake_recorders import RECORDER_PATHS


@pytest.mark.parametrize("path", RECORDER_PATHS)
def test_configui_defaults(path):
    """ Confirm there is default ConfigUI data for each fake recorder.
    """
    endaq.device.RECORDERS.clear()  # Clear cached devices, just to be safe
    dev = endaq.device.getRecorder(path, strict=False)
    assert ui_defaults.getDefaultConfigUI(dev) is not None
