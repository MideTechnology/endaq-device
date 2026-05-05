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

import time
from datetime import datetime
from datetime import timezone as tz
import sys
import glob
import os
from pathlib import Path
import shutil
from typing import Callable, List, Optional, Dict, Union, Any


# Helper class:
class Payload:
    payload = ''


@pytest.fixture(scope="session", autouse=True)
def hardware_creation(is_raspi):
    if is_raspi:
        print(f"Setting Raspi interface")
        hw = RaspiInterface()
    else:
        if not sys.stdin.isatty():
            hw = FakeInterface()
        else:
            hw = WindowsInterface()
    yield hw

@pytest.fixture
def hardware_interface(hardware_creation):
    if isinstance(hardware_creation, FakeInterface):
        pytest.skip("Skipping interactive test in non-interactive mode. Run pytest with -s option")
    yield hardware_creation

@pytest.fixture(scope="session")
def no_skip_hardware_interface(hardware_creation):
    yield hardware_creation

@pytest.fixture(scope="session", autouse=True)
def setupTeardownSession(no_skip_hardware_interface, fast_clean: bool):
    """ Set up and teardown GPIO RasPi controls at the beginning and end
        of a session.

        :param is_raspi: True if the tests are meant to run on a RaspberryPi,
            False otherwise. Set in command line.
    """
    # Put the device in default configuration
    print(f"Setting up session")
    config_dict = {"RecordingTimeLimit": 180}
    device = safe_get_device(unmounted=False, timeout=30)
    config = GeneralConfig(**config_dict)
    if config.set_configs(device, quick_config=True):
        print(f"Applying updated config")
        device.config.applyConfig()
        device.command.reset()  # Need to reset the device to turn the wifi on
        device = safe_get_device(timeout=30) # Wait for device to come back

    if fast_clean:
        # Always update the device configuration
        yield
    else:
        # Always update the device configuration
        print("\nSetting up RasPi...")
        no_skip_hardware_interface.set_usb(True)
        no_skip_hardware_interface.set_button(False)

        yield

        print("\nTearing down RasPi setup...")
        no_skip_hardware_interface.set_usb(True)
        no_skip_hardware_interface.set_button(False)

        # Only reset after the tests if the device is not present
        reset_device = False
        try:
            device = safe_get_device(unmounted=False)
            get_status(device)
            if device.command.status[1] != Status.IDLE:
                reset_device = True
        except endaq.device.exceptions.DeviceError as e:
            reset_device = True
        if reset_device:
            # if device is not connected, reset it
            no_skip_hardware_interface.set_usb(True)
            no_skip_hardware_interface.timed_button_press(20)

        print("\nDone with RasPi tear down.")

    print(f"Finished session")

@pytest.fixture # with a default scope of "function"
def setupTeardown(no_skip_hardware_interface, device_sn, fast_clean):
    """ Hard reset the enDAQ before and after every test, and load in the configuration.

        :param is_raspi: True if the tests are meant to run on a RaspberryPi,
            False otherwise. Set in command line.
        :param device_sn: the tested device's serial number collected from the 
            command line.
    """
    print(f"Setting up test")
    if fast_clean:
        yield
    else:
        # Setup
        # start up and connect
        print("\nSetting up...")
        start_time = time.time()
        no_skip_hardware_interface.set_usb(True)
        # Hold the button down to reset the device
        no_skip_hardware_interface.timed_button_press(18)
        # Connect to the device
        device = safe_get_device(device_sn, timeout=30, unmounted=False)
        # Set it to standard configuration
        config_dict = {"WifiEnable": 0, "PreRecordingDelay": 0, "RecordingTimeLimit": 120}
        config = GeneralConfig(**config_dict)
        if config.set_configs(device, quick_config=True):
            print(f"Applying config")
            device.config.applyConfig()
            time.sleep(5)               # Is the config not written fast enough or something? #TODO <- this could be related to the issue
            device.command.reset()      # Need to reset the device to turn the wifi on
            device = safe_get_device(device_sn, timeout=30, unmounted=False)

        yield # Runs test

        # Teardown
        no_skip_hardware_interface.set_usb(True)
        no_skip_hardware_interface.set_button(False)
        

        print(f"Test completed after {time.time() - start_time} seconds.")
    print(f"Test Done")

# # abstract tests
"""
Common actions that have tests associated with them, abstracted to be used across
multiple tests. These are not fixtures, and should not be called alone.
For uniformity, all methods should return a device.
"""

def start_recording(device, device_sn, status: Union[Status, List[Status]]):
    # Confirm device is recording
    device.command.startRecording()
    device = safe_get_device(device_sn, timeout=30, unmounted=True)
    if isinstance(status, Status): status = [status]
    assert wait_for_status(device, status)
    assert (device.command.status[1] in status
            ), f"Expected status {status}, received {device.command.status[1]}"
    return device

def stop_recording(device, device_sn, is_raspi):
    # Confirm device stopped recording
    if 20000 <= device.firmwareVersion <= 30100:
        assert stopRecOldFW(device, is_raspi) is None
    else:
        assert device.command.stopRecording() is True, "Device did not stop recording."
        
    device = safe_get_device(device_sn, timeout=30)
    wait_for_status(device, [Status.IDLE,
            Status.IDLE_UNMOUNTED])
    assert (device.command.status[1] == Status.IDLE or
        device.command.status[1] == Status.IDLE_UNMOUNTED), "Device is not idle."
    return device 

# # parametrization for the common marks

#triggers is a dict of channel id to config values. multiple triggers are allowed.
TRIGGER_DECORATOR = pytest.mark.parametrize("triggers", [ 
   {80: {"enabled": True, "high": 10}}
])
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


@pytest.mark.parametrize("params", ["default", "correct_path", "incorrect_path",
                                "unmounted_default", "unmounted_recording"])
def test_get_devices(params, device_sn, setupTeardown):
    """ Tests that 'getDevices()' works as intended.

        :param params: keywords representing a scenario to run in each of the
            parameterized tests.
        :param device_sn: the tested device's serial number collected from the
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up

    # Run different scenarios based on the "param" parameter
    match params:
        case "default":
            # Default parameters: Verify that expected device is returned
            device = endaq.device.getDevices()[0]
            assert device.serial == device_sn, "Incorrect device connected."
        case "correct_path":
            # Correct path specified: Verify that expected device is returned
            device = endaq.device.getDevices(
                paths=RECORDER_PATHS, unmounted=False, strict=False)
            assert device != [], f"Specified device was not returned: {device}"
        case "incorrect_path":
            # Incorrect path specified: Verify that nothing is returned
            device = endaq.device.getDevices(
                paths=("/abc/"), unmounted=False, strict=False)
            assert device == [], f"Device was returned: {device}"
        case "unmounted_default":
            # Unmounted = False: Verify that this normally returns the correct
            # device
            device = []
            device_list = endaq.device.getDevices(unmounted=False)
            for dev in device_list:
                if dev.serial == device_sn:
                    device.append(dev)
            assert device, "Incorrect device or no device connected."
        case "unmounted_recording":
            # Unmounted = False: Verify that if the device is recording, it is
            # not returned
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
    
@TRIGGER_DECORATOR
def test_trigger_standard_run(triggers, device_sn, setupTeardown, is_raspi):
    """
    Performs a standard run of an enDAQ device with triggers activated.
    Note that if triggers / values is a list, the other must be of equal size
    as well.
    
    :param trigger_keys: the channel value(s) for the triggers.
    :param values: The kwarg value(s) associated with each trigger. 
    """
    breakpoint()
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
    device.config.applyConfig()
    
    device = start_recording(device, serial_number, Status.TRIGGERING)
    #NOTE: We have no way of activating the device without a raspi 
    #NOTE: I don't actually know about this, it seems somewhat random?
    if is_raspi:
        #use hardware interface
        set_button(True)
        set_button(False) #so the button isn't being held down
        get_status(device)
        assert device.command.status[1] == Status.RECORDING
        
    assert device.serial == serial_number, "Did not reconnect to the same device." 


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