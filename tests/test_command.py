"""
Tests of the command interfaces.
"""

import os.path
import pytest

import endaq.device
from endaq.device import getRecorder
from endaq.device import command_interfaces

from .fake_recorders import RECORDER_PATHS

# Clear any cached devices, just to be safe
endaq.device.RECORDERS.clear()

# Create parameters, mainly to provide an ID, making the results readable
DEVICES = [pytest.param(getRecorder(path, strict=False), id=os.path.basename(path)) for path in RECORDER_PATHS]


@pytest.mark.parametrize("dev", DEVICES)
def test_command_basics(dev):
    """ Initial 'sanity test' to verify `CommandInterface` instances are
        being instantiated.
    """
    assert isinstance(dev.command, command_interfaces.CommandInterface)
