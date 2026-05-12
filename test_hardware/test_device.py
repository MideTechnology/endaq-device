"""
Automated tests for endaq.device.
"""
import endaq.device
from endaq.device import DeviceStatusCode as Status
from idelib.importer import importFile
import pytest

from test_hardware.helper_functions.general_config import GeneralConfig, GENERAL_CONFIG_IDS
from test_hardware.helper_functions.connection_helper import safe_get_device, wait_for_status, stopRecOldFW, get_status, safe_ping
from tests.fake_recorders import RECORDER_PATHS
from test_hardware.helper_functions.subtask_helpers import start_recording, stop_recording, make_recording 
from test_hardware.fixtures import noSkipHardwareInterface

import time
from datetime import datetime
import glob
import os
from pathlib import Path
#these imports are only used for creating fixtures. random should never
#be called in actual tests. For property based tests, use hypothesis


class Payload:
    payload = ''

TODO = lambda name : pytest.skip(f"Test {name} has not yet been implemented")
# ================= TESTS ================= # 
# # Standard tests.
def test_standard_run(device_sn, setupTeardown, is_raspi):
    """ Test a standard run of an enDAQ device.

        :param device_sn: the tested device's serial number collected from the
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up; Confirm device is idle
    device = safe_get_device(device_sn)
    serial_number = device.serial
     
    # Confirm device starts as idle
    get_status(device)       # Refresh the device status
    assert (
        device.command.status[1] == Status.IDLE or
        device.command.status[1] == Status.IDLE_UNMOUNTED), "Device is not idle."

    device = start_recording(device, serial_number, Status.RECORDING)
    
    assert device.serial == serial_number, "Did not reconnect to the same device."

    stop_recording(device, serial_number, is_raspi)

# This test only works if looped in sequential order. Random order is disabled
# for this reason.
@pytest.mark.random_order(disabled=True)
@pytest.mark.parametrize("index", range(1, 31))
def test_ping_payload(index, device_sn, setupTeardown):
    """ Tests that 'ping()' returns the input payload for a range of bytearray
        sizes.

        :param index: parameterized index of payload bitarray length.
        :param device_sn: the tested device's serial number collected from the
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Connect to device
    device = safe_get_device(device_sn)

    # Ensure the payload begins empty at start of loop
    if index == 1:
        Payload.payload == ''

    # Increase the length of the payload and send it to ping()
    Payload.payload += chr(index)
    returned_payload = safe_ping(device, bytearray(Payload.payload, 'utf-8'))
    print(f"\n{bytearray(Payload.payload, 'utf-8')} <-- Payload size {index}"
          f"\n{returned_payload} <-- Returned Payload")

    # Confirm that ping() returns the same thing it was sent
    assert returned_payload == bytearray(
        Payload.payload, 'utf-8'), f"ping() failed on size {index}."

def test_property_accuracy(device_sn, setupTeardown):
    """
    Tests that device properties of a "Real" Recorder are correct.
    """
    
    device = safe_get_device(device_sn, timeout=30)
    #for sake of modularity, information like birthday / channels aren't
    #checked.
    assert device.available and (device.available == device.config.available)
    assert device.config.name == device.name
    assert device.config.notes == device.notes
    assert device.canRecord
    assert device.hasConfigInterface
    assert device.command is not None and device.hasCommandInterface
    assert not device.isVirtual
    
def test_virtual_accuracy(device_sn, is_raspi, setupTeardown):
    """
    Tests that fields consistent between Virtual and "Real" recorders 
    are accurate.
    """
    device = safe_get_device(device_sn, timeout=30)
    start_recording(device, device_sn, Status.RECORDING)
    time.sleep(2) #arbitrary time, just to ensure file is created
    safe_ping(device)
    stop_recording(device, device_sn, is_raspi)
    safe_ping(device)
    rec_path = max(
        glob.glob(str(Path(device.path+f"/Data/{getattr(device.config, 'recordingDir', 'RECORD')}/*.IDE"))),
        key = os.path.getctime
    )
    ide_file = importFile(rec_path)
    virtual = endaq.device.Recorder.fromRecording(ide_file)

    assert device.name == virtual.name
    assert device.partNumber == virtual.partNumber
    assert device.productName == virtual.productName
    assert device.notes == virtual.notes
    assert device.birthday == virtual.birthday
    assert device.firmware == virtual.firmware
    assert device.firmwareVersion == virtual.firmwareVersion
    assert device.chipId == virtual.chipId

def test_unplug_device(device_sn, no_skip_hardware_interface):
    """
    Tests methods that produce different results when a device 
    is plugged in / unplugged.
    Note that this test assumes only one device is plugged in, and will fail otherwise
    """
    device = safe_get_device(device_sn)
    config_dict = {"WifiEnable": 0}
    config = GeneralConfig(**config_dict)
    if config.set_configs(device, quick_config=True):
        device.config.applyConfig()
    for usb_on, num_connected in iter([(False, 0), (True, 1)]):    
        no_skip_hardware_interface.set_usb(usb_on)
        time.sleep(10)
        assert (len(endaq.device.getDevices()) == num_connected
               ), f"getDevices detected {endaq.device.getDevices()}, when only {num_connected} is present"
        assert (len(endaq.device.getDeviceList()) == num_connected
               ), f"getDeviceList detected {endaq.device.getDevices()}, when only {num_connected} is present"

class TestGetDevices:
    def test_get_devices_default(self, device_sn, setupTeardown): 
        device = endaq.device.getDevices()[0]
        assert device.serial == device_sn, "Incorrect device connected."
        
    def test_get_devices_correct_path(self, device_sn, setupTeardown):
        device = endaq.device.getDevices(
            paths=RECORDER_PATHS, unmounted=False, strict=False)
        assert device != [], f"Specified device was not returned: {device}"
        
    def test_get_devices_incorrect_path(self, device_sn, setupTeardown): 
        device = endaq.device.getDevices(
            paths=("/abc/"), unmounted=False, strict=False)
        assert device == [], f"Device was returned: {device}"
        
    def test_get_devices_unmounted_default(self, device_sn, setupTeardown): 
        device = []
        device_list = endaq.device.getDevices(unmounted=False)
        for dev in device_list:
            if dev.serial == device_sn:
                device.append(dev)
        assert device, "Incorrect device or no device connected."
        
    def test_get_devices_unmounted_recording(self, device_sn, setupTeardown, is_raspi): 
        device = endaq.device.getDevices()[0]
        fw_version = device.firmwareVersion

        if 20000 <= fw_version <= 30100:
            device.command.startRecording()
            # Just delay for a bit to let the device start record
            time.sleep(15)
            new_device = endaq.device.getDevices(unmounted=False)
            dev_list = []
            for i in new_device:
                curr_dev = i
                if curr_dev.serial == device_sn:
                    dev_list.append(curr_dev)
            assert dev_list == [], "Device was returned while recording."
            stopRecOldFW(device, is_raspi) 
        else:
            start_recording(device, device_sn, Status.RECORDING)
            new_devices = endaq.device.getDevices(unmounted=False)
            dev_sn_list = [dev.serial for dev in new_devices]
            assert device_sn not in dev_sn_list, "Device was returned while recording."
            device.command.stopRecording()
                
@pytest.mark.skip("known bug")
def test_start_recording_wait(device_sn, setupTeardown, is_raspi):
    """ Tests that 'startRecording()' returns faster than the default case when
        'wait=False'.

        :param device_sn: the tested device's serial number collected from the
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    device = safe_get_device(device_sn)
    fw_version = device.firmwareVersion
    safe_ping(device)

    # Verify that the device's status begins as idle
    if fw_version > 30100:
        assert (device.command.status[1] ==
                Status.IDLE), "Device is not idle."

    # Running SR with wait=False; recording how long it takes; stop rec.
    false_start_time = time.time()
    device.command.startRecording(wait=False)
    false_end_time = time.time()
    false_execution_time = false_end_time - false_start_time
    wait_for_status(device, [Status.RECORDING])
    if 20000 <= fw_version <= 30100:
        stopRecOldFW(device, is_raspi)
        wait_for_status(device, [Status.IDLE])
    else:
        device.command.stopRecording()
        wait_for_status(device, [Status.IDLE])
        # Verify that the device's status is back to idle
    assert (device.command.status[1] ==
            Status.IDLE), "Device is not idle."

    device = safe_get_device(device_sn)

    # Running SR with wait=True; recording how long it takes; stop rec.
    default_start_time = time.time()
    device.command.startRecording()
    default_end_time = time.time()
    default_execution_time = default_end_time - default_start_time
    wait_for_status(device, [Status.RECORDING])
    device = stop_recording(device, device_sn, is_raspi)
    
    # Verify the wait=False case ran quicker than the wait=True case.
    print("wait=False:", false_execution_time,
            "wait=True:", default_execution_time)
    assert (false_execution_time < default_execution_time
            ), "Default returned quicker than when wait=False."

@pytest.mark.skip("known to not be working")
def test_start_recording_timeout(device_sn, setupTeardown, is_raspi):
    """ Tests that 'startRecording()' raises an Exception when 'timeout' is too low.

        :param device_sn: the tested device's serial number collected from the
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    device = safe_get_device(device_sn)
    device.refresh()
    fw_version = device.firmwareVersion

    # Since startRecording's behavior is firmware specific, its tests are too!
    if 20000 <= fw_version <= 30100:
        # Old FW doesn't seem to support the timeout param
        device.command.startRecording()
        stopRecOldFW(device, is_raspi)
    else:
        # Verify that if the timeout value is low enough, a DeviceTimeout
        # exception will be raised
        with pytest.raises(endaq.device.exceptions.DeviceTimeout) as exc_info:
            device.command.startRecording(wait=True, timeout=0.1)
        assert (exc_info.type == endaq.device.exceptions.DeviceTimeout
                ), "Didn't time out during startRecording."
        assert (str(exc_info.value) == "Timed out waiting for recording to start"
                ), "Wrong error message during timeout"

        device = safe_get_device(device_sn, timeout=30, unmounted=True)
        # If the device doesn't go back to idle, send a stop command, but otherwise let setup handle it
        if not wait_for_status(device, [Status.IDLE]):
            device.command.stopRecording()
                
# # Device change tests 
def test_set_config(device_sn, setupTeardown):
    """
    Test that we can set the device configuration and it will actually get written to the file and be retrievable
    """
    dev = safe_get_device(device_sn)
    
    old_name = dev.name
    test_name = f"T{time.time()}"
    
    dev.config.items[0x8FF7F].value = test_name
    
    dev.config.applyConfig()
    dev.command.reset()
    
    dev = safe_get_device(timeout=30, unmounted=False)
    
    initial_dev_name = dev.name
    dev.refresh()
    reload_dev_name = dev.config.items[0x8FF7F].value
    
    dev.config.items[0x8FF7F].value = old_name
    dev.config.applyConfig()
    error_list = []
    if test_name != initial_dev_name:
        error_list.append(f"Weird, reloaded device name did not reflect test name. Expected {test_name} got "
                          f"{initial_dev_name}. Initial name was {old_name}")
    if test_name != reload_dev_name:
        error_list.append(f"After rebooting the device, it did not keep the newly configured name. This probably means "
                          f"config.cfg was not flushed out to the device. Try mounting with the 'flush' option, or "
                          f"waiting up to 6 seconds between applying config and disconnecting. Expected {test_name} got "
                          f"{reload_dev_name}, initial name was {old_name}")
    assert len(error_list) == 0, "\n".join(error_list)

def test_bad_end(device_sn, is_raspi, setupTeardown):
    """
    Tests that calling end in unexpected cases (explained case by case in inline comments)
    is handled properly.
    In the case that the firmware version is incompatible, this test will be skipped
    """
    #TODO: make sure that the firmware is right. lower firmware versions will have the raspi stop
    #      recording, which wouldn't raise the error
    #attempts to call end before start is called.
    device = safe_get_device(device_sn, timeout=30)
    with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
        stop_recording(device, device_sn, is_raspi)
    assert str(excinfo.value) == "[ERR_INVALID_COMMAND -20] Badly formed command"
    #attempts to call end after already calling end
    start_recording(device, device_sn, Status.RECORDING)
    time.sleep(2)
    stop_recording(device, device_sn, is_raspi)

    with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
        stop_recording(device, device_sn, is_raspi)
    assert str(excinfo.value) == "[ERR_INVALID_COMMAND -20] Badly formed command"

@pytest.mark.parametrize('time_value, expected_out', [
    
])
def test_set_time(device_sn, setupTeardown, time_value, expected_out):
    TIME_TOLERANCE = 2 
    device = safe_get_device(device_sn)  
    start_time = time.time()
    device.command.setTime(time_value)
    elapsed_time = time.time() - start_time
    if expected_out < 946684800: #minimum time, Jan 1 2000. anything below will snap to it.
        assert device.command.get_time() - (946684800 + elapsed_time) <= TIME_TOLERANCE
    else:
        assert 0 <= device.command.get_time() - (expected_out + elapsed_time) <= TIME_TOLERANCE

    
class TestLock:    

    def test_bad_lockID(self, device_sn, setupTeardown):
        device = safe_get_device(device_sn)
        with pytest.raises(TypeError) as excinfo:
            device.command.setLockID(1)
        assert str(excinfo.value) == "Cannot encode int 1 as binary"
        with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
            device.command.setLockID(1)
        assert str(excinfo.value) == "[ERR_BAD_LOCK_ID -21] Command Lock ID invalid or already set"
    
    def test_standard_lock_run(self, device_sn, setupTeardown, is_raspi):
        device = safe_get_device(device_sn)
        assert device.command.setLockID()
        with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
            device.command.startRecording()
        assert str(excinfo.value) == "[ERR_BAD_LOCK_ID -21] Command Lock ID invalid or already set"
        lockID = device.command.getLockID()
        assert device.command.clearLockID(lockID)
        make_recording(device, device_sn, Status.RECORDING, is_raspi)

    def test_no_lock_props(self):
        device = None
        assert device.command.getLockID() is None
        assert device.command.isLocked() == (False, False) 
        #tests that clearing non-existant lockID doesn't break
        assert device.command.clearLockID()

def _change_cfg_value(cfg_item: endaq.device.config.ConfigItem):
    num_options = len(cfg_item.options)
    if num_options <= 1: 
        cfg_item.value = 1 if cfg_item.value != 1 else 0 #actual value / typing doesn't matter
    cfg_item.value = next((k for k, _ in cfg_item.options if cfg_item.value != k), None)

def test_get_revert_changes(device_sn, setupTeardown):
    """
    tests both get_changes and revert_changes
    """
    device = safe_get_device(device_sn)
    assert len(device.config.getChanges()) == 0
    for _, v in device.config.items.items():
        _change_cfg_value(v)
    assert len(device.config.getChanges()) == len(device.config.items)
    device.config.revert()
    assert len(device.config.getChanges()) == 0
    
def test_is_enabled(device_sn, setupTeardown):
    device = safe_get_device(device_sn)
    device.config.enableChannel(device.channels[80], enabled=True)
    assert device.config.isEnabled == True
    device.config.enableChannel(device.channels[80], enabled=False)
    assert device.config.isEnabled == False
    
def test_set_get_trigger(device_sn, setupTeardown):
    device = safe_get_device(device_sn)   
    
    device.config.setTrigger(device.channels[80], enabled=True, high = 10)
    device.config.applyConfig()
    device.getTrigger() == {'enabled': 1, 'high': 10}
    
    device.config.setTrigger(device.channels[80], enabled=False)
    device.config.applyConfig()
    device.getTrigger() == {'enabled': 0, 'high': 10}

def test_get_config_values(device_sn):
    device = safe_get_device(device_sn)
    config_vals = device.config.getConfigValues()
    for k,v in config_vals.items():
        if k in device.config.items: assert device.config.items[k].value == v

@pytest.mark.parametrize('sample_rate, is_valid', [
    *[(k, True) for k in [4000, 2000, 1000, 500, 250, 125, 63, 32, 16]],
    *[(k, False) for k in [3000, 1500, 780, 200]]
])
def test_sample_rate(device_sn, setupTeardown, sample_rate, is_valid):
    device = safe_get_device(device_sn)
    if is_valid:
        device.config.setSampleRate(device.channels[80], sample_rate)
        assert device.config.getSampleRate(device.channels[80]) == sample_rate
    else:
        with pytest.raises(ValueError):
            device.config.setSampleRate(device.channels[80], sample_rate)
            
def test_config_props(device_sn, setupTeardown):
    """
    tests that the properties in `device.config` match the 
    values that are assigned from the config.
    """
    device = safe_get_device(device_sn)
    attrs_to_test = ['retrigger', 'recordingStartTime', 'recordingSizeLimit', 
                     'recordingPrefix', 'recordingDir', 'pluginAction', 
                     'notes', 'name', 'buttonMode']
    attr_values = [1, int(datetime.now().timestamp()), 1, 
                   "recTMP", "recTMP", 1, 
                   "notesTMP", "nameTMP", "buttonModeTMP"]
    
    for attr, val in zip(attrs_to_test, attr_values):
        cfg_item = device.config.items[GENERAL_CONFIG_IDS[attr.capitalize()]]
        cfg_item.value = val
        device.config.applyConfig()
        assert getattr(device.config, attr) == val
    
   