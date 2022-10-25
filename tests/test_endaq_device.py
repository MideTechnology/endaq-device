import os.path
import pytest

import endaq.device

from .fake_recorders import RECORDER_PATHS


@pytest.mark.parametrize("path", RECORDER_PATHS)
def test_basic_identification(path):
    assert endaq.device.isRecorder(path, strict=False)


@pytest.mark.parametrize("path", RECORDER_PATHS)
def test_basic_instantiation(path):
    endaq.device.RECORDERS.clear()  # Clear any cached devices, just to be safe
    dev = endaq.device.getRecorder(path, strict=False)
    assert dev.partNumber == os.path.basename(path)

