"""
A file dedicated for functions that detect, identify, or retrieve information about devices, all of
which can be found at `docs.endaq.com/projects/endaq-device/en/latest/endaq/finding_devices.html`.
Note that almost all tests have the strict parameter will be asserting that it's equal to the non
strict version, as with our testing suite, the `strict` parameter will not change anything
"""
import pytest
import time
from typing import Literal, List
from endaq.device import Recorder #seperate import for typing
import endaq.device
from test_hardware.session_manager import SessionManager
TODO = lambda name: pytest.skip(f"Test {name} has not yet been implemented")

#pytest.skip(allow_module_level=True)
#==== Helper Functions ====#
pytest.skip(allow_module_level=True)
def validate_found_device(
        session_manager: SessionManager, 
        devices_found: List[Recorder], 
        min_conn: Literal["remote", "unmounted", "mounted"]) -> bool:
    """
    Validates that amongst the devices found, one of them is the device held by
    the session manager
    :param session_manager: the SessionManager found from the `session_manager` fixture. 
        Note that this is not plugged in automatically.
    :param devices_found: the devices to compare to the 
    :param min_conn: The minimum connection status to count as "found". eg: specifying 
        remote also includes any unmounted and mounted.

    :return: a boolean, True if the conditions were met, False otherwise
    """
    device_found = ""
    for device in devices_found:
        pass
    
    if min_conn != "remote":
        mounted = device_found.available
        return mounted if min_conn == "mounted" else not mounted  

    return device_found.isVirtual
#==========================#

@pytest.mark.parametrize('kwargs, exp_out', [

    ])
@pytest.mark.tty
@pytest.mark.no_wifi
def test_device_changed(session_manager, kwargs, exp_out):
    """
    Performs a series of changes to the device to ensure
    
    Note that the argument `recordersOnly` will always be set to True
    to minimize the possible false positive
    """
    #for current implementation, assuming set kwargs
    endaq.device.deviceChanged(clear=True) #clear any changes from previous tests
    #actions that cause connects / disconnects
    
    #actions that do not cause connects / disconnects
    #pings, changing (but not applying) config
    TODO("test_device_changed")

@pytest.mark.tty
class TestFindDevice:
    """
    Note that strict will always be set to True to minimize the 
    possible false positives. Also note that update can not be tested
    due to how the tester is set up.
    """

    def test_find_device_standard(self, session_manager, subtests):
        """
        Tests endaq.device.findDevices as it was intended.

        :param subtests: subtests is a built in pytest fixture used to 
            treat each assert as a subtest, in this case, similar to that of a parametrize.
        """
        device = session_manager.device
        
        test_kwargs = [ {'sn': device.serialInt}, {'sn': device.serial}]
        if device.chipId is not None: test_kwargs.append({'chipId': device.chipId})
        #parametrize can't be used here, subtests used instead.
        for kwargs in test_kwargs:
             with subtests.test():
                assert (validate_found_device(session_manager, [endaq.device.findDevice(**kwargs)])
                       ), f"device is not found with kwargs {kwargs}"
    
    def test_find_device_bad(self, session_manager, subtests):
        """
        Tests `endaq.device.findDevice` with incompatible
        values for sn / chipId.

        :param subtests: subtests is a built in pytest fixture used to 
            treat each assert as a subtest, in this case, similar to that of a parametrize.
        """
        device = session_manager.device
        invalid_test_kwargs = [{'sn': device.serialInt - 1}, {'sn': device.serial[:-1]}]
        if device.chipId is not None: invalid_test_kwargs.append({'chipId': device.chipId - 1})
        for kwargs in invalid_test_kwargs:
            with subtests.test():
                invalid_dev = endaq.device.findDevice(**kwargs) 
                assert ( invalid_dev == None
                        ), f"findDevice found device {invalid_dev} when an invalid parameter was given"
        
        if device.chipId is not None:
            with pytest.raises(ValueError):
                endaq.device.findDevice(sn = device.serial, chipId = device.chipId)

@pytest.mark.tty
@pytest.mark.no_wifi
def tet_get_recorder(session_manager):
    """
    we are unable to test the update parameter in getRecorder due to 
    only having a (consistent) singular device plugged in at a time.
    """
    dev_path = session_manager.device.patth
    TODO("test_get_recorder")
    #good path
    assert validate_found_device(
        session_manager, 
        [endaq.device.getRecorder(dev_path)]
     ) == True
    #bad path
    assert endaq.device.getRecorder('./') == None
    
@pytest.mark.tty
def test_is_recorder(session_manager):
    """
    """
    #good path
    
    #non root path (returns false)

    #bad path
    TODO("test_is_recorder")

@pytest.mark.tty
def test_on_recorder(session_manager):
    """
    """
    #on recorder
    p = session_manager.make_recording(5)
    assert endaq.device.onRecorder(p) == True
    assert endaq.device.onRecorder('./') == False

@pytest.mark.tty
def test_unplug_device(session_manager):
    """
    Tests methods that produce different results when a device 
    is plugged in / unplugged.
    """
    device = session_manager.device
    
    for is_connected in ([False, True]):
        session_manager.toggle_device_connection(usb=is_connected, mqtt=is_connected)
        time.sleep(10) #TODO: maybe awaitDisconnect / reconnect works here?

        assert (validate_found_device(session_manager, endaq.device.getDevices()) == is_connected
                ), (f'getDevices {['found', ' did not find'][is_connected]} device' 
                    f'when expected device is {['disconnected', 'connected'][is_connected]}')
        assert (validate_found_device(session_manager, endaq.device.getDevices()) == is_connected
               ) (f'getDeviceList {['found', ' did not find'][is_connected]} device' 
                    f'when expected device is {['disconnected', 'connected'][is_connected]}')
@pytest.mark.tty
@pytest.mark.wifi
def test_devices_found_wifi_only(session_manager):
    """
    Tests that the proper device is found when the only connection 
    source is the mqtt device.
    """
    session_manager.toggle_device_connection(usb=False, mqtt=True)
    time.sleep(10)
    assert (validate_found_device(session_manager, endaq.device.getDevices()) == True
            ), f"getDevices() couldn't find device when connected via MQTT but not USB"
    assert (validate_found_device(session_manager, endaq.device.getDeviceList()) == True
            ), f"getDeviceList() couldn't find device when connected via MQTT but not USB"

def test_get_devices_unmounted_recording(session_manager):
    """Tests that getDevices correctly reads a recording device as unmounted""" 
    device = session_manager.device
    device_sn = device.serial

    session_manager.start_recording()
    mounted_devices = endaq.device.getDevices(unmounted=False)
    serial_numbers = [device.serial for device in mounted_devices]
    assert device_sn not in serial_numbers, "Device was returned while recording." 

    session_manager.stop_recording()

