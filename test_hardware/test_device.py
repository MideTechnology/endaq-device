"""
Automated tests for endaq.device.
"""
import time
import pytest
from tests.fake_recorders import RECORDER_PATHS
import endaq.device
from pathlib import Path
from test_hardware.helper_functions.raspi_endaq_controller import set_button, set_usb, timed_button_press, _connect_device
from test_hardware.helper_functions.general_config import GeneralConfig
from test_hardware.helper_functions.connection_helper import safe_get_device, wait_for_status, stopRecOldFW

# Helper class:
class Payload:
    payload = ''


@pytest.fixture(scope="session", autouse=True)
def setupTeardownGPIO(is_raspi):
    """ Set up and teardown GPIO RasPi controls at the beginning and end
        of a session.

        :param is_raspi: True if the tests are meant to run on a RaspberryPi,
            False otherwise. Set in command line.
    """
    if is_raspi is True:
        print("\nSetting up RasPi...")
        set_usb(True)
        set_button(False)

    yield

    if is_raspi is True:
        print("\nTearing down RasPi setup...")
        set_usb(True)
        timed_button_press(20)
        print("\nDone with RasPi tear down.")


@pytest.fixture # with a default scope of "function"
def setupTeardown(is_raspi, device_sn):
    """ HArd reset the enDAQ before and after every test, and load in the configuration.

        :param is_raspi: True if the tests are meant to run on a RaspberryPi,
            False otherwise. Set in command line.
        :param device_sn: the tested device's serial number collected from the 
            command line.
    """
    # Setup
    # start up and connect
    print("\nSetting up...")
    if is_raspi is True:
        set_usb(True)
        # Hold the button down to reset the device
        timed_button_press(20)
    # Connect to the device
    device = safe_get_device(device_sn, timeout=20)
    # Set it to standard configuration
    config_dict = {"WifiEnable": 0, "PreRecordingDelay": 0, "RecordingTimeLimit": 120}
    config = GeneralConfig(**config_dict)
    if config.set_configs(device, quick_config=True):
        device.config.applyConfig()
        device.command.reset()      # Need to reset the device to turn the wifi on
        device = safe_get_device(device_sn, timeout=20)
    
    yield # Runs test

    # Teardown
    if is_raspi is True:
        set_usb(True)
        set_button(False)
    print("\nTest complete.")


# Tests:
def test_standard_run(device_sn, setupTeardown, is_raspi):
    """ Test a standard run of an enDAQ device.

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up; Confirm device is idle
    timeout = 30
    device = safe_get_device(device_sn)
    fw_version = device.firmwareVersion
    serial_number = device.serial

    if 20000 <= fw_version <= 30100:
        device.command.startRecording()
        stopRecOldFW(device, is_raspi)
    else:
        # Confirm device starts as idle
        assert (
            device.command.status[1] is endaq.device.DeviceStatusCode.IDLE or
            endaq.device.DeviceStatusCode.IDLE_UNMOUNTED), "Device is not idle."

        # Confirm device is recording
        device.command.startRecording()
        wait_for_status(device, [endaq.device.DeviceStatusCode.RECORDING], timeout=timeout)
        assert (device.command.status[1] == endaq.device.DeviceStatusCode.RECORDING
                ), "Device is not recording. Status was not 10."

        # Clear cached device
        device.refresh()
        assert device.available == False, "Device is still cached"
        device = safe_get_device(device_sn, timeout=5)
        assert device.serial == serial_number, "Did not reconnect to the same device."

        # Confirm device stopped recording
        assert device.command.stopRecording() is True, "Device did not stop recording."
        wait_for_status(device, [endaq.device.DeviceStatusCode.IDLE,
                endaq.device.DeviceStatusCode.IDLE_UNMOUNTED], timeout=timeout)
        assert (device.command.status[1] is endaq.device.DeviceStatusCode.IDLE or
                endaq.device.DeviceStatusCode.IDLE_UNMOUNTED), "Device is not idle."


@pytest.mark.parametrize("command, status_code",
                         [("battery", endaq.device.DeviceStatusCode.IDLE),
                          ("startRecording", endaq.device.DeviceStatusCode.RECORDING),
                          ("stopRecording", endaq.device.DeviceStatusCode.IDLE),
                          ])
def test_ping_status(command, status_code, device_sn, setupTeardown):
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
    timeout = 5
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
                wait_for_status(device, [status_code], timeout=timeout)
            case "startRecording":
                device.command.startRecording()
                wait_for_status(device, [status_code], timeout=timeout)
            case "stopRecording":
                device.command.startRecording()
                wait_for_status(device, [endaq.device.DeviceStatusCode.RECORDING], timeout=timeout)
                device.command.stopRecording()
                wait_for_status(device, [status_code], timeout=timeout)

        # Verify the device has the correct status depending on what command was run
        device.command.ping()
        assert (device.command.status[1] == status_code
                ), f"Status was {device.command.status[1]} instead of {status_code}."

        # If the device is recording, stop it
        if device.command.status[1] == endaq.device.DeviceStatusCode.RECORDING:
            device.command.stopRecording()
            # Don't need to wait for the stop to complete, teardown/cleanup should handle it


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
    returned_payload = device.command.ping(bytearray(Payload.payload, 'utf-8'))
    print(f"\n{bytearray(Payload.payload, 'utf-8')} <-- Payload size {index}"
          f"\n{returned_payload} <-- Returned Payload")

    # Confirm that ping() returns the same thing it was sent
    assert returned_payload == bytearray(
        Payload.payload, 'utf-8'), f"ping() failed on size {index}."


@pytest.mark.parametrize("params", ["default", "correct_path", "incorrect_path",
                                    "unmounted_default", "unmounted_recording"])
def test_get_devices(params, device_sn, setupTeardown, is_raspi):
    """ Tests that 'getDevices()' works as intended.

        :param params: keywords representing a scenario to run in each of the 
            parameterized tests.
        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    timeout = 5

    # Run different scenarios based on the "param" parameter
    match params:
        case "default":
            # Default parameters: Verify that expected device is returned
            device = safe_get_device(device_sn)
            assert device.serial == device_sn, "Incorrect device connected."
        case "correct_path":
            # Correct path specified: Verify that expected device is returned
            device = endaq.device.getDevices(
                paths=RECORDER_PATHS, unmounted=False, strict=False)
            assert device != [], f"Specified device was not returned: {device}"
        case "incorrect_path":
            # Incorrect path specified: Verify that nothing is returned
            device = endaq.device.getDevices(
                paths=(RECORDER_PATHS[0] + "abc"), unmounted=False, strict=False)
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
            device = safe_get_device(device_sn)
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
                device.command.startRecording()
                wait_for_status(device, [endaq.device.DeviceStatusCode.RECORDING], timeout)
                assert (device.command.status[1] == endaq.device.DeviceStatusCode.RECORDING
                        ), "Device is not recording."
                new_device = endaq.device.getDevices(unmounted=False)
                dev_sn_list = [dev.serial for dev in new_device]
                assert device_sn not in dev_sn_list, "Device was returned while recording."
                device.command.stopRecording()


def test_start_recording_default(device_sn, setupTeardown, is_raspi):
    """ Tests that 'startRecording()' works as expected in a default scenario.

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    timeout = 10
    device = safe_get_device(device_sn)
    fw_version = device.firmwareVersion

    # Since startRecording's behavior is firmware specific, its tests are too!
    if 20000 <= fw_version <= 30100:
        device.command.startRecording()
        stopRecOldFW(device, is_raspi)
    else:
        # Verify the device starts with an idle status
        assert (device.command.status[1] ==
                endaq.device.DeviceStatusCode.IDLE), "Device is not idle."

        # Start recording and next verify that the drive is absent at first
        device.command.startRecording()
        device.refresh()
        assert device.command.available == False, "Device drive is not absent."

        # Verify the device's status is recording and the drive is available
        # again now that we have waited
        wait_for_status(device, [endaq.device.DeviceStatusCode.RECORDING], timeout)
        assert (device.command.status[1] == endaq.device.DeviceStatusCode.RECORDING
                ), "Device is not recording."
        assert device.command.available == True, "Device drive is not available."

        # Stop recording and verify the device's status is now idle
        device.command.stopRecording()
        wait_for_status(device, [endaq.device.DeviceStatusCode.IDLE], timeout)
        assert (device.command.status[1] == endaq.device.DeviceStatusCode.IDLE
                ), f"Device is not idle. It is {device.command.status[1]}"


def test_start_recording_wait(device_sn, setupTeardown, is_raspi):
    """ Tests that 'startRecording()' returns faster than the default case when 
        'wait=False'. 

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    timeout = 10
    device = safe_get_device(device_sn)
    device.refresh()  # remove this once endaq.device is fixed
    fw_version = device.firmwareVersion

    # Verify that the device's status begins as idle
    if fw_version > 30100:
        assert (device.command.status[1] ==
                endaq.device.DeviceStatusCode.IDLE), "Device is not idle."

    # Running SR with wait=False; recording how long it takes; stop rec.
    time.sleep(5)
    false_start_time = time.time()
    device.command.startRecording(wait=False)
    false_end_time = time.time()
    false_execution_time = false_end_time - false_start_time
    wait_for_status(device, [endaq.device.DeviceStatusCode.RECORDING], timeout)
    if 20000 <= fw_version <= 30100:
        stopRecOldFW(device, is_raspi)
        wait_for_status(device, [endaq.device.DeviceStatusCode.IDLE], timeout)
    else:
        device.command.stopRecording()
        wait_for_status(device, [endaq.device.DeviceStatusCode.IDLE], timeout)
        # Verify that the device's status is back to idle
    assert (device.command.status[1] ==
            endaq.device.DeviceStatusCode.IDLE), "Device is not idle."

    device.refresh()
    device = safe_get_device(device_sn)

    # Running SR with wait=True; recording how long it takes; stop rec.
    time.sleep(5)
    default_start_time = time.time()
    device.command.startRecording()
    default_end_time = time.time()
    default_execution_time = default_end_time - default_start_time
    wait_for_status(device, [endaq.device.DeviceStatusCode.RECORDING], timeout)
    if 20000 <= fw_version <= 30100:
        stopRecOldFW(device, is_raspi)
        wait_for_status(device, [endaq.device.DeviceStatusCode.IDLE], timeout)
    else:
        device.command.stopRecording()
        wait_for_status(device, [endaq.device.DeviceStatusCode.IDLE], timeout)
        # Verify that the device's status is back to idle
        assert (device.command.status[1] ==
                endaq.device.DeviceStatusCode.IDLE), "Device is not idle."

    # Verify that the device's status is back to idle.
    assert (device.command.status[1] ==
            endaq.device.DeviceStatusCode.IDLE), "Device is not idle."

    # Verify the wait=False case ran quicker than the wait=True case.
    print("wait=False:", false_execution_time,
            "wait=True:", default_execution_time)
    assert (false_execution_time < default_execution_time
            ), "Default returned quicker than when wait=False."


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
        
        # If the device doesn't go back to idle, send a stop command, but otherwise let setup handle it
        if not wait_for_status(device, [endaq.device.DeviceStatusCode.IDLE], timeout=10):
            device.command.stopRecording()
