"""
Tests of the command interfaces.
"""

import os.path
import pytest

import endaq.device
from endaq.device import getRecorder
from endaq.device.command_interfaces import CommandInterface, FileCommandInterface

from .fake_recorders import RECORDER_PATHS
from .mock_hardware import MockCommandSerialIO

# Clear any cached devices, just to be safe
endaq.device.RECORDERS.clear()

# Create parameters, mainly to provide an ID, making the results readable
DEVICES = [pytest.param(getRecorder(path, strict=False), id=os.path.basename(path)) for path in RECORDER_PATHS]

SERIAL_DEVICES = [param for param in DEVICES if not isinstance(param[0][0].command, FileCommandInterface)]


@pytest.mark.parametrize("dev", DEVICES)
def test_command_basics(dev):
    """ Initial 'sanity test' to verify `CommandInterface` instances are
        being instantiated.
    """
    assert isinstance(dev.command, CommandInterface)


@pytest.mark.parametrize("dev", SERIAL_DEVICES)
def test_command_ping(dev):
    """ Test the `ping()` command on devices that support it.
    """
    mock_io = MockCommandSerialIO(dev)
    mock_io.response = mock_io.encodeResponse({'EBMLResponse':
                                               {'ResponseIdx': dev.command.index + 1,
                                                'CMDQueueDepth': 1,
                                                'DeviceStatusCode': 0,
                                                'PingReply': bytearray(b'hello')}},
                                              resultcode=0)
    
    assert dev.command.ping() == bytearray(b'hello')
