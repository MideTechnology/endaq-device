"""
Initial 'sanity check' identification and instantiation tests. Perform early.
"""

import os.path
from glob import glob
import idelib.importer
import pytest

import endaq.device

from . import fake_recorders

# Create parameters, mainly to provide an ID, making the results more readable
RECORDER_PATHS = [pytest.param(path, id=os.path.basename(path))
                  for path in fake_recorders.RECORDER_PATHS]


TEST_ROOT = os.path.dirname(__file__)
IDE_FILES = glob(os.path.join(TEST_ROOT, 'recordings', '*.IDE'))


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
    assert dev.path == path
    assert dev.partNumber == os.path.basename(path).partition('_')[0]


@pytest.mark.parametrize("path", RECORDER_PATHS)
def test_basic_caching(path):
    """ Test that previously created recorders are cached and reused.
    """
    dev = endaq.device.getRecorder(path, strict=False)
    dev2 = endaq.device.getRecorder(path, strict=False)
    assert dev is dev2

    # Clear cache and verify new recorders are created
    endaq.device.RECORDERS.clear()
    dev3 = endaq.device.getRecorder(path, strict=False)
    assert dev is not dev3


def test_getDevices():
    """ Test of `getDevices()`, comparing found device paths to the list of
        fake recorder directories.
    """
    endaq.device.RECORDERS.clear()
    devs = endaq.device.getDevices(paths=fake_recorders.RECORDER_PATHS,
                                   strict=False,
                                   unmounted=False)
    assert sorted(dev.path for dev in devs) == sorted(fake_recorders.RECORDER_PATHS)

    # Just one path provided should return just one device
    devs = endaq.device.getDevices(paths=fake_recorders.RECORDER_PATHS[0],
                                   strict=False,
                                   unmounted=False)
    assert len(devs) == 1


@pytest.mark.parametrize("path", RECORDER_PATHS)
def test_onRecorder(path):
    """ Test checking if a file is on a recorder (its path corresponds
        to a recorder's path).
    """
    endaq.device.RECORDERS.clear()
    dev = endaq.device.getRecorder(path, strict=False)
    assert endaq.device.onRecorder(dev.infoFile, strict=False)


@pytest.mark.parametrize("path", RECORDER_PATHS)
def test_findDevice(path):
    """ Test finding recorders by serial number.
    """
    with pytest.raises(ValueError):
        # ValueError: Either a serial number or chip ID is required
        endaq.device.findDevice(paths=fake_recorders.RECORDER_PATHS,
                                strict=False)

    with pytest.raises(ValueError):
        # ValueError: Either a serial number or chip ID is required, not both
        endaq.device.findDevice(sn=1234,
                                chipId=0xabcd,
                                paths=fake_recorders.RECORDER_PATHS,
                                strict=False)

    # Nonexistent serial number
    assert not endaq.device.findDevice(sn=-1,
                                       paths=fake_recorders.RECORDER_PATHS,
                                       strict=False)

    dev = endaq.device.getRecorder(path, strict=False)
    endaq.device.RECORDERS.clear()

    assert endaq.device.findDevice(dev.serialInt,
                                   paths=fake_recorders.RECORDER_PATHS,
                                   strict=False)
    assert endaq.device.findDevice(sn=dev.serialInt,
                                   paths=fake_recorders.RECORDER_PATHS,
                                   strict=False)
    assert endaq.device.findDevice(sn=dev.serial,
                                   paths=fake_recorders.RECORDER_PATHS,
                                   strict=False)

    if dev.chipId:
        # Very old HW/FW does not report a chip ID
        assert endaq.device.findDevice(chipId=dev.chipId,
                                       paths=fake_recorders.RECORDER_PATHS,
                                       strict=False)


@pytest.mark.parametrize("filename", IDE_FILES)
def test_fromRecording(filename):
    """ Test instantiation from an IDE file.
    """
    doc = idelib.importer.importFile(filename, quiet=True)
    dev = endaq.device.fromRecording(doc)

    assert dev.partNumber in filename

    # Sanity checks: Make sure channels/sensors/transforms were created
    # TODO: More detailed check of contents, and/or basic type checks?
    assert dev.channels
    assert dev.sensors
    assert dev.transforms
