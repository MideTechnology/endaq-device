"""
Automated tests for endaq.device.
"""
import endaq.device
from endaq.device import DeviceStatusCode as Status
from idelib.importer import importFile
import pytest

from test_hardware.helper_functions.hardware_interface import HardwareInterface, RaspiInterface, WindowsInterface, FakeInterface
from test_hardware.helper_functions.general_config import GeneralConfig
from test_hardware.helper_functions.connection_helper import safe_get_device, wait_for_status, stopRecOldFW, get_status, safe_ping
from test_hardware.helper_functions.raspi_endaq_controller import set_usb, set_button
from tests.fake_recorders import RECORDER_PATHS
from test_hardware.helper_functions.subtask_helpers import start_recording, stop_recording, make_recording, config_name_from_id 
from test_hardware.fixtures import noSkipHardwareInterface

import time
from datetime import datetime
from datetime import timezone as tz
import sys
import glob
import os
from typing import Callable, List, Optional, Dict, Union, Any
from pathlib import Path
#these imports are only used for creating fixtures. random should never
#be called in actual tests. For property based tests, use hypothesis
import random
import string
import shutil


# Helper class:
class Payload:
    payload = ''

TODO = lambda name : pytest.skip(f"Test {name} has not yet been implemented")
RANDOM_NAME = lambda k: random.choices(string.ascii_letters, k=k)
    
# # parametrization for the common marks

#TODO: make this config_id based
#triggers is a dict of channel id to config values. multiple triggers are allowed.
TRIGGER_DECORATOR = pytest.mark.parametrize("triggers", [ 
   {80: {"enabled": True, "high": 10}}
])

#TODO: fill in with values
OFFSET_DECORATOR = pytest.mark.parametrize("offset", [
    30, 60, 128, 0, -5
])

TIME_DECORATOR = pytest.mark.parametrize("config_time", [
    30, 60, 128, 0, -5])
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
    fw_version = device.firmwareVersion
    serial_number = device.serial
     
    # Confirm device starts as idle
    get_status(device)       # Refresh the device status
    assert (
        device.command.status[1] == Status.IDLE or
        device.command.status[1] == Status.IDLE_UNMOUNTED), "Device is not idle."

    device = start_recording(device, serial_number, Status.RECORDING)
    
    assert device.serial == serial_number, "Did not reconnect to the same device."

    stop_recording(device, serial_number, is_raspi)

@pytest.mark.parametrize("command, status_code",
                         [("battery", Status.IDLE),
                          ("startRecording", Status.RECORDING),
                          ("stopRecording", Status.IDLE),
                          ])
def test_ping_status(command, status_code, device_sn, is_raspi, setupTeardown):
    """ Tests that 'ping()' accurately updates the device's status.

        :param command: The device command that impacts the status code.
        :param status_code: The device status returned in the response to a
            command.
        :param device_sn: the tested device's serial number collected from the
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    device = safe_get_device(device_sn)
    fw_version = device.firmwareVersion

    if 20000 <= fw_version <= 30100:
        # Old FW does not support updating the device's status so this test
        # does not apply
        assert True
    else:
        # Run different scenarios based on the command parameter
        match command:
            case "battery":
                device.command.getBatteryStatus()
                wait_for_status(device, [status_code])
            case "startRecording":
                device.command.startRecording()
                device = safe_get_device(device_sn, timeout=30, unmounted=True)
                wait_for_status(device, [status_code])
            case "stopRecording":
                device.command.startRecording()
                device = safe_get_device(device_sn, timeout=30, unmounted=True)
                wait_for_status(device, [Status.RECORDING])
                device.command.stopRecording()
                device = safe_get_device(device_sn, timeout=30)
                wait_for_status(device, [status_code])

        # Verify the device has the correct status depending on what command was run
        get_status(device)
        assert (device.command.status[1] == status_code
                ), f"Status was {device.command.status[1]} instead of {status_code}."

        # If the device is recording, stop it
        if device.command.status[1] == Status.RECORDING:
            stop_recording(device, device_sn, is_raspi)
            
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
    #TODO: update with device.config.recordingDir
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
        
    def test_get_devices_unmounted_recording(self, device_sn, setupTeardown): 
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
                stopRecOldFW(device, is_raspi)      # FIXME: Fix this
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
def test_start_recording_timeout(device_sn, setupTeardown):
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
    
    dev.config.items[589695].value = test_name
    
    dev.config.applyConfig()
    dev.command.reset()
    
    dev = safe_get_device(timeout=30, unmounted=False)
    
    initial_dev_name = dev.name
    dev.refresh()
    reload_dev_name = dev.config.items[589695].value
    
    dev.config.items[589695].value = old_name
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

'''
NOTE: these two tests are currently disabled due to an incoming rework to general_config.py
@pytest.mark.parametrize("disable_trigger_channel", [False, True])
@TRIGGER_DECORATOR
def test_trigger_standard_run(triggers, disable_trigger_channel, device_sn, setupTeardown, is_raspi):
    """
    Performs a standard run of an enDAQ device with triggers activated.
    Note that if triggers / values is a list, the other must be of equal size
    as well.
    
    :param trigger_keys: the channel value(s) for the triggers.
    :param values: The kwarg value(s) associated with each trigger. 
    """
    # Set up; Confirm device is idle
    device = safe_get_device(device_sn)
    fw_version = device.firmwareVersion
    serial_number = device.serial
    old_conf = device.config.getConfig()     
    # Confirm device starts as idle
    get_status(device)       # Refresh the device status
    assert (
        device.command.status[1] == Status.IDLE or
        device.command.status[1] == Status.IDLE_UNMOUNTED), "Device is not idle."
    
    for ch_id, v in triggers.items():
        device.config.setTrigger(device.channels[ch_id], **v)
        if disable_trigger_channel: device.config.
    device.config.applyConfig()
    
    device = start_recording(device, serial_number, Status.TRIGGERING)
        
    assert device.serial == serial_number, "Did not reconnect to the same device." 
    device = stop_recording(device, device_sn, is_raspi)
    devoce.config.applyConfig(oldConf)

#TODO: merge with above.
@TRIGGER_DECORATOR
def test_trigger_on_disabled_channel(triggers, device_sn, is_raspi, setupTeardown, triggerCleanup):
    """
    Tests that triggers do not effect the recording process if the 
    channel is disabled
    """
    # Set up; Confirm device is idle
    device = safe_get_device(device_sn)
    fw_version = device.firmwareVersion
    serial_number = device.serial
    # Confirm device starts as idle
    get_status(device)       # Refresh the device status
    assert (
        device.command.status[1] == Status.IDLE or
        device.command.status[1] == Status.IDLE_UNMOUNTED), "Device is not idle."
    #disable a channel
    for ch_id, v in triggers.items():
        v["enabled"] = False
        device.config.setTrigger(chs[ch_id], **v)
    device.config.applyConfig()
    #we are checking that the status goes to RECORDING instead of TRIGGERING
    device = start_recording(device, serial_number, Status.RECORDING)
    
    assert device.serial == serial_number, "Did not reconnect to the same device."

    stop_recording(device, serial_number, is_raspi)
'''
@TIME_DECORATOR
def test_max_recording_time(device_sn, is_raspi, is_prod, config_time, triggerCleanup):
    """
    Tests that the Recording Time limit is respected. Note that this test has an internal
    margin of error, to where if the device reported it's status within 0.5 seconds of 
    the config time, it is assumed that it might have been reported wrong, and the test will be ran again
    with a higher config_time
    """
    _max_recording_tst(device_sn, is_raspi, is_prod, config_time)
    
def _max_recording_tst(device_sn, is_raspi, is_prod, conig_time):
    """
    helper function for test_max_recording time, allowing the test
    to be re-run in the case of tolerances.
    """
    TOLERANCE = 0.25 
    device = safe_get_device(device_sn)
    config = GeneralConfig(RecordingTimeLimit=config_time)
    if config.set_configs(device, quick_config=True):
        device.config.applyConfig()
        device.command.reset()
        device = safe_get_device(device_sn)
    start_time = time.time()
    start_recording(device, device_sn, [Status.TRIGGERING, Status.RECORDING])
    stop_code = wait_for_status([Status.TRIGGERING, Status.RECORDING])
    time_delta = time.time() - start.time
    if time_delta - config_time < TOLERANCE:
        assert stop_code == Status.TRIGGERING
    elif time_delta - config_time > TOLERANCE:
        assert stop_code == Status.RECORDING
    elif is_prod:
        #TODO: is this print or logging?
        print("time spent on test within tolerances, rerunning test with increased recording time")
        _max_recording_tst(device_sn, is_raspi, is_prod, config_time + TOLERANCE)
    else:
        pytest.skip("time spent on test within tolerances. Use --production to get an assert value, computation will take longer")

#TODO: trigger decorator
@TIME_DECORATOR
def test_delay_then_trigger(device_sn, is_raspi, is_prod, config_time, triggerCleanup):
    """
    Tests that delay then trigger works as expected.
    """
    _delay_then_trigger_tst(device_sn, is_raspi, is_prod, config_time)
            
def _delay_then_trigger_tst(device_sn, is_raspi, is_prod, config_time):
    """
    Helper function for test_delay_then_trigger, allowing the function to be re-called
    in case the timing values were within error.
    """
    TOLERANCE = 0.25 
    #TODO: apply config
    start_time = time.time()
    stop_code = wait_for_status([Status.TRIGGERING, Status.IDLE])
    time_delta = time.time() - start.time
    if time_delta - config_time < TOLERANCE:
        assert stop_code == Status.RECORDING
    elif time_delta - config_time > TOLERANCE:
        assert stop_code == Status.IDLE
    elif is_prod:
        #TODO: is this print or logging?
        print("time spent on test within tolerances, rerunning test with increased recording time")
        _max_recording_tst(device_sn, is_raspi, is_prod, config_time + TOLERANCE)
    else:
        pytest.skip("time spent on test within tolerances. Use --production to get an assert value, computation will take longer")

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

@pytest.mark.prod_only
@OFFSET_DECORATOR
def test_start_at_time(device_sn, setupTeardown, triggerCleanup, is_raspi, offset):
    """
    Tests that the `start_at_time` config option works as intended.

    NOTE: This test is marked prod_only as this test will take multiple minutes to run.
    """
    device = safe_get_device(device_sn)
    now = int(datetime.now(tz.utc).timestamp())
    new_time = now + offset
    device.config.items[1048447].value = new_time 
    device.config.applyConfig()
    if offset <= 0:
        start_recording(device, device_sn, Status.RECORDING) 
    else:
        start_recording(device, device_sn, Status.TRIGGERING)
        #assert triggering
        time.sleep(offset)
        wait_for_status(device, [Status.RECORDING])
    
    stop_recording(device, device_sn, is_raspi)

#TODO: change to use NEW_NAME
def test_recdir_change(device_sn, is_raspi):
    """
    tests that changing the recording directory works as intended
    """
    device = safe_get_device(device_sn)
    #create new directory
    if not hasattr(device.config, 'recordingDir'):
        pytest.skip("device is unable to change recording directory, test is not needed")
    rec_dir = f"{device.path}/DATA"
    new_loc = device.config.recordingDir + "TMP"
    erase_after = not new_loc in [dir for dir in os.listdir(rec_dir) if os.path.isdir(dir)] 
    last_recording = glob.glob(f"{rec_dir}/{new_loc}/*.IDE")
    last_recording = None if not erase_after or len(last_recording) == 0 else max(last_recording, key = os.path.getctime)
    
    device.config.recordingDir = new_loc
    device.config.applyConfig()
    
    start_recording(device, device_sn, Status.RECORDING)
    time.sleep(2)
    stop_recording(device, device_sn, is_raspi)
    assert new_loc in os.listdir(rec_dir)
    if erase_after:
        shutil.rmtree(f"{rec_dir}/{new_loc}")
        device.config.applyConfig()
    else:
        assert max(glob.glob(f"{rec_dir}/{new_loc}/*.IDE"), key = os.path.getctime) != last_recording       
    #revert config path back to original
    device.config.recordingDir = new_loc[:-3]
    device.config.applyConfig()     
    
def test_max_recording_time(device_sn):
    TODO("test_max_recording_time")

class TestButtonMode:
    #used to assert that startRecording / stopRecording still works
    #as intended. self.command_independence is an alias of make_recording
    
    def _universal_setup(self, device_sn, button_value):
        """
        Retrieves and applies the common config setup between all tests
        :return: the endaq device associated with the device_sn
        """
        device = safe_get_device(device_sn)
        device.config.items[1113983].value = button_value
        device.config.applyConfig()
        return device
        
    def test_button_mode_instant(self, device_sn, no_skip_hardware_interface, is_raspi, setupTeardown):
        device = self._universal_setup(device_sn, 0)
        no_skip_hardware_interface.timed_button_press(0.3)
        wait_for_status(device, [Status.RECORDING])
        assert device.command.status[1] == Status.RECORDING
        stop_recording(device, device_sn, is_raspi)
        make_recording(device, device_sn, Status.RECORDING, is_raspi)

    @pytest.mark.skip("inconsistent behavior, debugging")
    def test_button_mode_hold(self, device_sn, no_skip_hardware_interface, is_raspi, setupTeardown):
        #assert that tapping doesn't work
        device = self._universal_setup(device_sn, 1)
        breakpoint()
        no_skip_hardware_interface.timed_button_press(0.3)
        wait_for_status(device, [Status.IDLE])
        assert device.command.status[1] == Status.IDLE

        no_skip_hardware_interface.timed_button_press(1.5)
        wait_for_status(device, [Status.RECORDING])
        assert device.command.status[1] == Status.RECORDING
        #assert that can stop recording
        
        no_skip_hardware_interface.timed_button_press(1.5)
        wait_for_status(device, [Status.IDLE])
        assert device.command.status[1] == Status.IDLE
        make_recording(device, device_sn, Status.RECORDING, is_raspi)
        
    def test_button_mode_no_stop(self, device_sn, no_skip_hardware_interface, is_raspi, setupTeardown):
        device = self._universal_setup(device_sn, 2)
        no_skip_hardware_interface.timed_button_press(1.5)
        wait_for_status(device, [Status.RECORDING])
        assert device.command.status[1] == Status.RECORDING
        
        #assert that button press doesn't work
        no_skip_hardware_interface.timed_button_press(1.5)
        wait_for_status(device, [Status.RECORDING])
        assert device.command.status[1] == Status.RECORDING
        stop_recording(device, device_sn, is_raspi)
        #TODO: assert that command stop still works
        make_recording(device, device_sn, Status.RECORDING, is_raspi)


@pytest.mark.parametrize("plugin_action_value, rec_status", [
    (0, Status.IDLE),
    (1, Status.RECORDING)
])
@TRIGGER_DECORATOR #TODO, this needs to be implemented
def test_plugin_action(device_sn, setupTeardown, no_skip_hardware_interface, triggers, plugin_action_value, rec_status):
    device = safe_get_device(device_sn)
    # ignore usb during recordings, needed for test 
    device.config.items[3014527].value = 1
    plugin_action_item = device.config.items[3080063]
    plugin_action_item.value = plugin_action_value
    device.config.applyConfig()
    no_skip_hardware_interface.unplug_replug(1)
    wait_for_status(device, [rec_status])
    #TODO: better strings.
    assert device.command.status[1] == rec_status
    if rec_status == Status.RECORDING:
        stop_recording(device, device_sn, is_raspi)

def test_pre_recording_delay():
    TODO("test_pre_recording_delay")

@pytest.mark.parametrize('rec_size', [
-10, 0, 50, 100, 500, 987])
def test_max_recording_size(device_sn, setupTeardown, newDir, rec_size):
    if rec_size < 0:
        #assert that it raises value error
    elif rec_size == 0:
        pytest.skip('0kb recording is equivalent to a standard run, ignoring')
    else:
        
    #this should probably be done in a new dir so we can delete and not run out of space
    TODO("test_max_recording_size")

@pytest.mark.parametrize('time_value, expected_out', [
    
])
def test_set_time(device_sn, time_value, expected_out):
   TODO("test_set_time") 

def test_delay_trigger_settings():
    TODO("test_delay_or_trigger")
	
    
class TestLock:
    def test_standard_lock_run(self):
        TODO("test_standard_lock_run")

    def test_invalid_lock_settings(self):
        #set lock id to something unhashable

        #trying to set a 
        TODO("test_invalid_lock_settings")

    def test_no_lock_props(self):
        device = None
        
        assert device.command.isLocked() == (False, False) 
        TODO("test_no_lock_props")

def test_get_changes():
    TODO("test_get_changes")

#TODO: this might need to converted to use pytest.param
@pytest.mark.parametrize("ch_id", [
    ()
])
def test_get_sample_rate(device_sn, ch_id):
    TODO("test_get_sample_rate")

@pytest.mark.paramemtrize('cfg_id, ch_id', [
    (),
    ()
])
def test_is_enabled(device_sn, cfg_id, setupTeardown):
    device = safe_get_device(device_sn)
    
    for cfg_val, assert_val in [(0, False), (1, True)]:
        device.config.items[cfg_id].value = cfg_val
        device.config.applyConfig()
        assert device.config.isEnabled(device.channels[ch_id]) == b
        

@pytest.mark.parametrize('cfg_id', [
])
def test_get_trigger(device_sn, cfg_id):
    TODO("test_get_trigger")
    #assert that getTrigger work
    
    #assert that getTriggers has that as that as the only channel activated.

def test_change_recording_file_prefix(device_sn):
    #get name wih no uses

    #make recording, ensure that's that is the only one of it's name, called *name*_000001.IDE

    #go back to none, make sure it goes back to original, and there are n + 1 of that recording number
    TODO("test_change_recording_file_prefix")

def test_get_config_values(device_sn):
    TODO("test_get_config_values")

def test_set_time_default(device_sn):
    device = safe_get_device(device_sn)
    
    TODO("test_set_time_default")

def test_retrigger():
    """
    
    """

    #NOTE: we test the validity of max_recording_length in test `test_max_recording_time`
    #and will use it in this test.
    TODO("test_retrigger_basic")
	
def test_UTC_offset(device_sn, setupTeardown, triggerCleanup, is_raspi, newDir):
    """
    Tests that setting the UTC offset in the config has the proper effects,
    explained in inline comments
    """
    
    UTC_config_item = device.config.items[1048447]
    device = safe_get_device(device_sn)
    default_offset = UTC_config_item.value
    #create recording
    create_recording(device, device_sn, Status.RECORDING, is_raspi)
    newest_rec = max(glob.glob(f"{newDir}/*.IDE"), key = os.path.getctime)
    UTC_config_.value = default_offset - 60 * 60 #1 hour backwards
    create_recording(device, device_sn, Status.RECORDING, is_raspi)
    #assert the previous recording (with the future time zone) is the newest
    assert newest_rec == max(glob.glob(f"{newDir}/*.IDE"), key = os.path.getctime)
    UTC_config_item.value = default_offset + 2 * 60 * 60 #forward 2 hours
    create_recording(device, device_sn, Status.RECORDING, is_raspi)
    all_recs = glob.glob(f"{rec_dir}/{newDir}/*.IDE")
    assert newest_rec != max(all_recs, key = os.path.getctime)
    TODO("test_UTC_offset")
