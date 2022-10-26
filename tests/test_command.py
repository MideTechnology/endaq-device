import pytest

import endaq.device
from endaq.device import command_interfaces

from .fake_recorders import RECORDER_PATHS

endaq.device.RECORDERS.clear()  # Clear any cached devices, just to be safe
DEVICES = [endaq.device.getRecorder(path, strict=False) for path in RECORDER_PATHS]


@pytest.mark.parametrize("dev", DEVICES)
def test_command_basics(dev):
    """ Confirm there is default ConfigUI data for each fake recorder.
    """
    assert isinstance(dev.command, command_interfaces.CommandInterface)
