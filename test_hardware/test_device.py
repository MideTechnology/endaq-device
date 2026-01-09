"""
Automated tests for endaq.device.
"""
import time
import pytest
from tests.fake_recorders import RECORDER_PATHS
import endaq.device
from pathlib import Path
from test_hardware.raspi_endaq_controller import set_button, set_usb, timed_button_press

# Helper class:
class Payload:
    payload = ''


# Helper functions and fixtures:
def commandWait(device, timeout):
    """ Wait for the device to reconnect after a command is sent.

        :param device: Connected device.
        :param timeout: Time (seconds) to wait for the device to reconnect.
    """

    for _ in range(int(timeout)):
        try:
            resp = device.command.ping()
            print(f"Status code: {device.command.status=}\t"
                  "message: {dev.command.status[1]}")
            if device.command.status[1] == endaq.device.response_codes.DeviceStatusCode.RECORDING or \
                    device.command.status[1] == endaq.device.response_codes.DeviceStatusCode.IDLE_UNMOUNTED:
                print(
                    f"Device is recording. Status code: {device.command.status[1]}")

        except Exception as e:
            print(f"Got error {e}")

        # Getting here means that either expected_path is none and devices still
        # connected or the specific device path has not left yet
        time.sleep(1)


def assertSN(device_sn, timeout: int=0):
    """ Find the connected device that matches the inputted serial number and
        set it to the "device" variable. If there is no device with a matching
        SN, raise an exception.
        
        :param device_sn: the tested device's serial number collected from the 
            command line.
        :return: device matching the inputted SN.
    """
    start_time = time.time()
    num_dev = len(endaq.device.getDevices(unmounted=False))

    while num_dev == 0 and time.time() - start_time < timeout:
        num_dev = len(endaq.device.getDevices(unmounted=False))

    if num_dev == 0:
        raise endaq.device.exceptions.DeviceError("No device found.")
    elif num_dev == 1:
        device = endaq.device.getDevices()[0]
        assert (device.serial == device_sn), "Not connected to the correct device."
    else:
        for index in range(num_dev):
            device = endaq.device.getDevices()[index]
            if device.serial == device_sn:
                break
        if device.serial != device_sn:
            raise endaq.device.exceptions.DeviceError("No device with that SN is connected.")

    return device


def stopRecOldFW(device, is_raspi):
    """ On an ALREADY RECORDING device with FW <= 3.01.00, check that running
        'stopRecording()' raises an exception and then use a simulated button
        press (ONLY WORKS ON RASPI) to stop the recording.

        :param device: Connected device.
    """
    if is_raspi is False:
        assert False, "Can't run test on old firmware unless it's connected to a RasPi setup."

    # Attempt to run stop recording and catch the thrown exception
    commandWait(device, 5)
    with pytest.raises(endaq.device.exceptions.CommandError) as exc_info:
        device.command.stopRecording()

    # Simulated button press to stop recording
    timed_button_press(1)

    # Check the device with old FW raised an exception
    assert (exc_info.type == endaq.device.exceptions.CommandError
            ), "Old FW didn't error out on stopRecording."


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
        set_button(False)
        print("\nDone with RasPi tear down.")


@pytest.fixture # with a default scope of "function"
def setupTeardown(is_raspi, device_sn):
    """ Properly reset the enDAQ before and after every test.

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
        # Wait a bit for it to come back
        time.sleep(15)
        # Make sure lines are in the right state
    device = assertSN(device_sn)
    # clear any config files off the device
    conf = (Path(device.path)/"SYSTEM/config.cfg")
    if conf.is_file():
        conf.unlink()
    
    # Stop the device if it is recording
    device.command.ping()
    if device.command.status[1] == endaq.device.response_codes.DeviceStatusCode.RECORDING:
        device.command.stopRecording()
        commandWait(device, 10)

    yield # Runs test

    # Teardown
    print("\nTearing down...")
    commandWait(device, 5)
    if device.command.status[1] == endaq.device.response_codes.DeviceStatusCode.RECORDING:
        device.command.stopRecording()
        commandWait(device, 10)
    # disconnect and shut down
    if is_raspi is True:
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
    timeout = 10
    device = assertSN(device_sn)
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
        commandWait(device, timeout)
        assert (device.command.status[1] == endaq.device.DeviceStatusCode.RECORDING
                ), "Device is not recording. Status was not 10."

        # Clear cached device
        device.refresh()
        assert device.available == False, "Device is still cached"
        device = assertSN(device_sn)
        assert device.serial == serial_number, "Did not reconnect to the same device."

        # Confirm device stopped recording
        assert device.command.stopRecording() is True, "Device did not stop recording."
        commandWait(device, timeout)
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
    device = assertSN(device_sn)
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
                commandWait(device, timeout)
            case "startRecording":
                device.command.startRecording()
                commandWait(device, timeout)
            case "stopRecording":
                device.command.startRecording()
                commandWait(device, timeout)
                device.command.stopRecording()
                commandWait(device, timeout)

        # Verify the device has the correct status depending on what command was run
        device.command.ping()
        assert (device.command.status[1] == status_code
                ), f"Status was {device.command.status[1]} instead of {status_code}."

        # If the device is recording, stop it
        if device.command.status[1] == endaq.device.DeviceStatusCode.RECORDING:
            device.command.stopRecording()
            commandWait(device, timeout)


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
    device = assertSN(device_sn)

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
            device = assertSN(device_sn)
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
            device = assertSN(device_sn)
            fw_version = device.firmwareVersion

            if 20000 <= fw_version <= 30100:
                device.command.startRecording()
                commandWait(device, timeout)
                new_device = endaq.device.getDevices(unmounted=False)
                dev_list = []
                for i in new_device:
                    curr_dev = i
                    if curr_dev.serial == device_sn:
                        dev_list.append(curr_dev)
                assert dev_list == [], "Device was returned while recording."
                stopRecOldFW(device, is_raspi)
                commandWait(device, timeout)
            else:
                device.command.startRecording()
                commandWait(device, timeout)
                assert (device.command.status[1] == endaq.device.DeviceStatusCode.RECORDING
                        ), "Device is not recording."
                new_device = endaq.device.getDevices(unmounted=False)
                dev_list = []
                for i in new_device:
                    curr_dev = i
                    if curr_dev.serial == device_sn:
                        dev_list.append(curr_dev)
                assert dev_list == [], "Device was returned while recording."
                commandWait(device, timeout)
                device.command.stopRecording()
                commandWait(device, timeout)


def test_start_recording_default(device_sn, setupTeardown, is_raspi):
    """ Tests that 'startRecording()' works as expected in a default scenario.

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    timeout = 10
    device = assertSN(device_sn)
    fw_version = device.firmwareVersion
    commandWait(device, timeout)

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
        commandWait(device, timeout)
        assert (device.command.status[1] == endaq.device.DeviceStatusCode.RECORDING
                ), "Device is not recording."
        assert device.command.available == True, "Device drive is not available."

        # Stop recording and verify the device's status is now idle
        device.command.stopRecording()
        commandWait(device, timeout)
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
    device = assertSN(device_sn)
    device.refresh()  # remove this once endaq.device is fixed
    fw_version = device.firmwareVersion
    commandWait(device, timeout)

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
    commandWait(device, timeout)
    if 20000 <= fw_version <= 30100:
        stopRecOldFW(device, is_raspi)
        commandWait(device, timeout)
    else:
        device.command.stopRecording()
        commandWait(device, timeout)
        # Verify that the device's status is back to idle
        assert (device.command.status[1] ==
                endaq.device.DeviceStatusCode.IDLE), "Device is not idle."

    device.refresh()
    device = assertSN(device_sn)

    # Running SR with wait=True; recording how long it takes; stop rec.
    time.sleep(5)
    default_start_time = time.time()
    device.command.startRecording()
    default_end_time = time.time()
    default_execution_time = default_end_time - default_start_time
    commandWait(device, timeout)
    if 20000 <= fw_version <= 30100:
        stopRecOldFW(device, is_raspi)
        commandWait(device, timeout)
    else:
        device.command.stopRecording()
        commandWait(device, timeout)
        # Verify that the device's status is back to idle
        assert (device.command.status[1] ==
                endaq.device.DeviceStatusCode.IDLE), "Device is not idle."

    # Verify that the device's status is back to idle.
    assert (device.command.status[1] ==
            endaq.device.DeviceStatusCode.IDLE), "Device is not idle."

    # Verify the wait=False case ran quicker than the wait=True case.
    print("false:", false_execution_time,
            "true:", default_execution_time)
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
    device = assertSN(device_sn)
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
        commandWait(device, timeout=10)

        # Stop recording and verify the device is idle
        device.command.stopRecording()
        commandWait(device, timeout=10)
        assert (device.command.status[1] ==
                endaq.device.DeviceStatusCode.IDLE), "Device is not idle."
