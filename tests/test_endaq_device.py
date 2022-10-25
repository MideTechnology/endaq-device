import os.path
import pytest

from endaq.device import getRecorder


RECORDERS_ROOT = os.path.join(os.path.dirname(__file__), 'fake_recorders')
RECORDERS = [os.path.join(RECORDERS_ROOT, d) for d in os.listdir(RECORDERS_ROOT)
             if not d.startswith(('.', '_'))]


@pytest.mark.parametrize("path", RECORDERS)
def test_basic_instantiation(path):
    dev = getRecorder(path, strict=False)
    assert dev.partNumber == os.path.basename(path)

