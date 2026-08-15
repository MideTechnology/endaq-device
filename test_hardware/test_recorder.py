"""
A file containing tests dedicated to the tests
regarding the `Recorder` class found in
`docs.endaq.com/projects/endaq-device/en/latest/endaq/Recorder.html`
"""
import endaq.device
from endaq.device.measurement import (ANY, ACCELERATION, ALTITUDE, ANG_RATE, AUDIO, DIRECTION,
                                      FREQUENCY, GENERIC, GYRO, HUMIDITY, LIGHT, LOCATION, 
                                      MAGNETIC, ORIENTATION, PRESSURE, ROTATION, SPEED,
                                      TEMPERATURE, TIME, VOLTAGE, get_measurement_type)
from idelib.importer import importFile
from ebmlite import loadSchema
import time
import pytest

TODO = lambda name: pytest.skip(f" Test {name} has not yet been implemented")

@pytest.mark.skip("TestVirtualAccuracy not implemented yet")
class TestVirtualAccuracy:
    """
    A series of tests used to test the validity of real device to Recorder conversion
    """

    def test_virtual_accuracy_channels(self, session_manager):
        device = session_manager.device
        virtual = endaq.device.fromRecording(session_manager.make_recording())
        ch = device.channels[80]
        assert device.getAccelRange(ch) == virtual.getAccelRange(ch)
        assert device.getAccelAxisChannels(ch) == virtual.getAccelAxisChannels(ch)


    def test_virtual_accuracy_cals(self, session_manager):
        """
        tests the accuracy of the calibration retrieval functions, both user
        and non-user generated. Note that this doesn't test anything embl related,
        that is in `test_virtual_accuracy_embl`
        """
        device = session_manager.device
        virtual = endaq.device.fromRecording(session_manager.make_recording()) 
        for b in [False, True]:
            assert device.getCalDate(b) == virtual.getCalDate(b)
            assert device.getCalExpiration(b) == virtual.getCalExpiration(b)
            assert device.getCalPolynomials(b) == virtual.getCalPolynomials(b)
            assert device.getCalibration(b) == virtual.getCalibration(b)
    
    def test_virtual_accuracy_props(self, session_manager):
        device = session_manager.device
        virtual = endaq.device.fromRecording(session_manager.make_recording())

        assert device.name == virtual.name
        assert device.partNumber == virtual.partNumber
        assert device.productName == virtual.productName
        assert device.notes == virtual.notes 
        assert device.birthday == virtual.birthday
        assert device.firmware == virtual.firmware
        assert device.firmwareVersion == virtual.firmwareVersion
        assert device.chipId == virtual.chipIdV
    
    def test_virtual_accuracy_funcs(self, session_manager):
        """
        tests that the recorder methods that are shared between
        physical and virtual devices return the same outputs
        """
        device = session_manager.device
        virtual = endaq.device.fromRecording(session_manager.make_recording())    
        assert device.getSensors() == virtual.getSensors()
        assert device.getProperties() == virtual.getProperties()
        assert device.getManifest() == virtual.getManifest()

    def test_virtual_accuracy_embl(self, session_manager):
        """
        tests the accuracy of the calibration tests based on the ebml files
        """
        #
        TODO('test_virtual_accuracy_embl')

def test_write_get_user_cal(session_manager):
    TODO('test_write_get_user_cal')

def test_get_time_accuracy(session_manager):
    """
    tests that the getTime parameter is equivalent
    between the command interface and the recorder class.
    a more comprehensive set of getTime can be found 
    in `test_command.py`
    """
    TIME_BUFFER = 1 #to account for edge cases that come with getting time in full seconds.
    device = session_manager.device
    start_time = time.time()
    device.getTime()
    elapsed = time.time() - start_time

    TODO('test_get_set_time_accuracy')

def test_set_time_accuracy(session_manager):
    """
    tests that the getTime parameter is equivalent
    between the command interface and the recorder class.
    a more comprehensive set of getTime can be found 
    in `test_command.py`
    """
    OFFSET = -500
    time_to_set = time.time() + OFFSET  
    TIME_BUFFER = 1
    device = session_manager.device
    start_time = time.time()
    device.setTime(time_to_set)
    elapsed = time.time() - start_time
    assert abs(device.getTime()[0] - (time_to_set + elapsed)) < TIME_BUFFER +abs(OFFSET)

@pytest.mark.parametrize("mtype", [
    ACCELERATION, ALTITUDE, ANG_RATE, AUDIO, DIRECTION, FREQUENCY, GENERIC, GYRO, 
    HUMIDITY, LIGHT, LOCATION, MAGNETIC, ORIENTATION, PRESSURE, ROTATION, SPEED,
    TEMPERATURE, TIME, VOLTAGE
])
def test_get_channels_gmt(session_manager, mtype):
    """
    tests that every channel gotten from getChannels has the correct measurement
    type, determined by `endaq.device.measurement.get_measurement_type`.
    """
    device = session_manager.device
    for k, _ in device.getChannels(mtype).items():
        gmt_filtered = get_measurement_type(device.channels[k])
        assert mtype in gmt_filtered, ( 
            f"getChannels for type {mtype} got channel {(k, device.channels[k])}, "
            f"but was not included by get_measurement_type, getting {gmt_filtered}"
                )

def test_get_any_channels(session_manager):
    """
    A variant on `test_get_channel` explictly testing the mtype = Any case
    """
    device = session_manager.device
    #all channels have a channel of type `ANY` 
    assert len(device.channels) == len(device.getChannels(ANY))
    #default type of NONE should be the same as ANY
    assert device.getChannels() == device.getChannels(ANY)

def test_get_clock_drift(session_manager):
    """
    Tests that getClockDrift correctly reacts in reference to changing
    the internal device time
    """
    TODO('test_get_clock_drift')
    
def test_get_info():
    """
    """
    TODO('test_get_info')

def test_get_manifest(session_manager):
    #superset of getInfo, but is spread across certain fields
    
    TODO('test_get_manifest')

def test_get_subchannel_range(session_manager):
    """
    NOTE: for most subchannels, they may not have the same measurement type
    and or range of the other subchannels.
    """    
    TODO('test_get_subchannel_range')

