import pytest

from endaq.device import CommandError, getRecorder
from endaq.device.response_codes import DeviceStatusCode

from . import mock_client
from .fake_recorders import RECORDER_PATHS

DEVICE = getRecorder(RECORDER_PATHS[-1], strict=False)

# ===========================================================================
#
# ===========================================================================

command, client = mock_client.createMocks(DEVICE)


def test_client_basics():
    """ Basic command test.
    """
    # A supported command
    assert command.ping(b'hello world')  == b'hello world'

    # An unsupported command
    with pytest.raises(CommandError):
        command.startRecording()
    assert command.response[1] == DeviceStatusCode.ERR_UNKNOWN_COMMAND


def test_client_lockID():
    """ Test getting, setting, releasing LockID.
    """
    assert command.getLockID() is None

    command.setLockID()
    assert command.getLockID() == command.hostId

    command.clearLockID()
    assert command.getLockID() is None


def test_client_getInfo():
    """ Test GetInfo.
    """
    # Basic: no lock required
    assert command._getInfo(0) == client.DEVINFO

    # Basic: Nonexistent index
    with pytest.raises(CommandError):
        command._getInfo(1)
    assert command.response[1] == DeviceStatusCode.ERR_BAD_INFO_INDEX

    # Info index requiring lock, but no lock
    with pytest.raises(CommandError):
        command._getInfo(5)
    assert command.response[1] == DeviceStatusCode.ERR_BAD_LOCK_ID

    # Info index requiring lock, lock set
    command.setLockID()
    assert command._getInfo(5, lock=True) == client.CONFIG
