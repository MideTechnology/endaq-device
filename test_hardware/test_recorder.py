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
import pytest

TODO = lambda name: pytest.skip(f" Test {name} has not yet been implemented")

@pytest.mark.skip("TestVirtualAccuracy not implemented yet")
class TestVirtualAccuracy:
    """
    A series of tests used to test the validity of real device to Recorder conversion
    """
    def _new_rec(self, session_manager) -> endaq.device.Recorder:
        """
        
        """
        pytest.skip("_new_rec has not been implemented yet")
        session_manager.make_recording()
        #get the recording
        virt_path = ...
        with importFile(virt_path) as f:
            return endaq.device.fromRecording(f)

    def test_virtual_accuracy_channels(self, session_manager):
        device = session_manager.device
        virtual = self._new_rec(session_manager)
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
        virtual = self._new_rec(session_manager=session_manager)

        for b in [False, True]:
            assert device.getCalDate(b) == virtual.getCalDate(b)
            assert device.getCalExpiration(b) == virtual.getCalExpiration(b)
            assert device.getCalPolynomials(b) == virtual.getCalPolynomials(b)
            assert device.getCalibration(b) == virtual.getCalibration(b)
    
    def test_virtual_accuracy_props(self, session_manager):
        device = session_manager.device
        virtual = self._new_rec(session_manager=session_manager)

        assert device.name == virtual.name
        assert device.partNumber == virtual.partNumber
        assert device.productName == virtual.productName
        #assert device.notes == virtual.notes TODO: bug?
        assert device.birthday == virtual.birthday
        assert device.firmware == virtual.firmware
        assert device.firmwareVersion == virtual.firmwareVersion
        assert device.chipId == virtual.chipIdV
    
    def test_virtual_accuracy_funcs(self, session_manager):
        """
        tests the methods on 
        """
        device = session_manager.device
        virtual = self._new_rec(session_manager=session_manager)
        
        assert device.getSensors() == virtual.getSensors()
        assert device.getProperties() == virtual.getProperties()
        assert device.getManifest() == virtual.getManifest()

    def test_virtual_accuracy_embl(self, session_manager):
        """
        tests the accuracy of the calibration tests based on the ebml files
        """
        TODO('test_virtual_accuracy_embl')

def test_write_get_user_cal(session_manager):
    TODO('test_write_get_user_cal')

def test_get_set_time_accuracy(session_manager):
    """
    tests that the getTime and setTime parameters are equivalent
    between the command interface and the recorder class.
    a more comprehensive set of getTime and setTime can be found 
    in `test_command.py`
    """
    TODO('test_get_set_time_accuracy')


@pytest.mark.parametrize("mtype", [
    ACCELERATION, ALTITUDE, ANG_RATE, AUDIO, DIRECTION, FREQUENCY, GENERIC, GYRO, 
    HUMIDITY, LIGHT, LOCATION, MAGNETIC, ORIENTATION, PRESSURE, ROTATION, SPEED,
    TEMPERATURE, TIME, VOLTAGE
])
def test_get_channels(session_manager, mtype):
    """
    
    """
    #for channel, check to see that every channel in there is of the correct type
    TODO('test_get_channels')

def test_get_any_channels(session_manager):
    """
    A variant on `test_get_channel` explictly testing the mtype = Any case
    """
    TODO('test_get_any_channels')

def test_get_clock_drift(session_manager):
    """

    """
    TODO('test_get_clock_drift')
    
def test_get_info():
    """
    """
    TODO('test_get_info')

def test_get_manifest():
    #superset of getInfo
    TODO('test_get_manifest')

def test_get_subchannel_range():
    TODO('test_get_subchannel_range')

def test_start_recording():
    """
    Tests that the non-command interface start recording works as intended.
    Essentially a mirrror of `test_standard_run` in the `test_command.py` file.
    """
    TODO('test_start_recording')


