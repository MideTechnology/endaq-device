import os.path
import pytest

import endaq.device

from .fake_recorders import RECORDER_PATHS


@pytest.mark.parametrize("path", RECORDER_PATHS)
def test_basic_identification(path):
    """ Basic test of recorder identification. All test 'fake recorders'
        should be identified.
    """
    assert endaq.device.isRecorder(path, strict=False)


def test_identification_negative():
    """ Test a non-recorder path to verify it isn't misidentified.
    """
    # Using the test file's directory because it's handy.
    assert not endaq.device.isRecorder(os.path.dirname(__file__))


@pytest.mark.parametrize("path", RECORDER_PATHS)
def test_basic_instantiation(path):
    """ Basic test of recorder instantiation. All test 'fake recorders'
        should instantiate `Recorder` subclasses.
    """
    endaq.device.RECORDERS.clear()  # Clear any cached devices, just to be safe
    dev = endaq.device.getRecorder(path, strict=False)
    assert dev.partNumber == os.path.basename(path)
