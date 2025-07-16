"""
Automated tests for endaq.device.
"""
import time
import pytest
import RPi.GPIO as GPIO
from tests.fake_recorders import RECORDER_PATHS
import endaq.device


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


@pytest.fixture(scope="session", autouse=True)
def setupTeardownGPIO():
    """ Set up and teardown GPIO RasPi controls at the beginning and end
        of a session.
    """
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(15, GPIO.OUT) # Pin 15 is GPIO22
    GPIO.setup(13, GPIO.OUT) # Pin 13 is GPIO27

    yield

    GPIO.cleanup()


@pytest.fixture # with a default scope of "function"
def setupTeardown():
    """ Properly reset the enDAQ before and after every test.
    """
    # Setup
    # start up and connect
    print("Setting up...")
    GPIO.output(15, GPIO.LOW) # GPIO22 set Low
    GPIO.output(13, GPIO.LOW) # GPIO27 set Low
    time.sleep(15)
    device = endaq.device.getDevices()[0]
    device.command.ping()
    if device.command.status[1] == endaq.device.response_codes.DeviceStatusCode.RECORDING:
        device.command.stopRecording()

    yield # Runs test

    # Teardown
    print("Tearing down...")
    commandWait(device, 5)
    if device.command.status[1] == endaq.device.response_codes.DeviceStatusCode.RECORDING:
        device.command.stopRecording()
    # disconnect and shut down
    GPIO.output(13, GPIO.HIGH) # GPIO27 set High
    time.sleep(10)
    print("Test complete")


# Tests:
def test_standard_run(device_sn, setupTeardown):
    """ Test a standard run of an enDAQ device.

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up; Confirm device is idle
    timeout = 10
    device = endaq.device.getDevices()[0]
    serial_number = device.serial
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
    device = endaq.device.getDevices()[0]
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
    device = endaq.device.getDevices()[0]

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
    device = endaq.device.getDevices()[0]

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
    timeout = 5

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
                paths=(RECORDER_PATHS[0] + "abc"), unmounted=False, strict=False)
            assert device == [], f"Device was returned: {device}"
        case "unmounted_default":
            # Unmounted = False: Verify that this normally returns the correct
            # device
            device = endaq.device.getDevices(unmounted=False)[0]
            assert device.serial == device_sn, "Incorrect device connected."
        case "unmounted_recording":
            # Unmounted = False: Verify that if the device is recording, it is
            # not returned
            device = endaq.device.getDevices()[0]
            device.command.startRecording()
            commandWait(device, timeout)
            assert (device.command.status[1] == endaq.device.DeviceStatusCode.RECORDING
                    ), "Device is not recording."
            new_device = endaq.device.getDevices(unmounted=False)
            assert new_device == [], "Device was returned while recording."
            commandWait(device, timeout)
            device.command.stopRecording()
            commandWait(device, timeout)


def test_start_recording_default(device_sn, setupTeardown):
    """ Tests that 'startRecording()' works as expected in a default scenario.

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    timeout = 10
    device = endaq.device.getDevices()[0]
    fw_version = device.firmwareVersion
    commandWait(device, timeout)

    # Since startRecording's behavior is firmware specific, its tests are too!
    match fw_version:
        case a if 20000 <= a <= 20100:
            # Recordings can only be started, no status response. Command may be
            # unstable, fix is to unplug/replug USB
            assert False, "Firmware version not yet supported."
        case b if 20100 < b < 30000:
            # Recordings can only be started, no status response
            assert False, "Firmware version not yet supported."
        case c if 30000 <= c <= 30100:
            # Recordings can only be started, no status response
            assert False, "Firmware version not yet supported."
        case d if 30100 < d:
            # Recordings can be started, stopped, and device will send status
            # while recording

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
        case _:
            assert False, "Firmware version not supported."


def test_start_recording_wait(device_sn, setupTeardown):
    """ Tests that 'startRecording()' returns faster than the default case when 
        'wait=False'. 

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    timeout = 10
    device = endaq.device.getDevices()[0]
    device.refresh()  # remove this once endaq.device is fixed
    fw_version = device.firmwareVersion
    commandWait(device, timeout)

    # Since startRecording's behavior is firmware specific, its tests are too!
    match fw_version:
        case a if 20000 <= a <= 20100:
            # Recordings can only be started, no status response. Command may be
            # unstable, fix is to unplug/replug USB
            assert False, "Firmware version not yet supported."
        case b if 20100 < b < 30000:
            # Recordings can only be started, no status response
            assert False, "Firmware version not yet supported."
        case c if 30000 <= c <= 30100:
            # Recordings can only be started, no status response
            assert False, "Firmware version not yet supported."
        case d if 30100 < d:
            # Recordings can be started, stopped, and device will send status
            # while recording

            # Verify that the device's status begins as idle
            assert (device.command.status[1] ==
                    endaq.device.DeviceStatusCode.IDLE), "Device is not idle."

            # Running SR with wait=False; recording how long it takes; stop rec.
            time.sleep(5)
            false_start_time = time.time()
            device.command.startRecording(wait=False)
            false_end_time = time.time()
            false_execution_time = false_end_time - false_start_time
            commandWait(device, timeout)
            device.command.stopRecording()
            commandWait(device, timeout)

            # Verify that the device's status is back to idle
            assert (device.command.status[1] ==
                    endaq.device.DeviceStatusCode.IDLE), "Device is not idle."

            device.refresh()
            device = endaq.device.getDevices()[0]

            # Running SR with wait=True; recording how long it takes; stop rec.
            time.sleep(5)
            default_start_time = time.time()
            device.command.startRecording()
            default_end_time = time.time()
            default_execution_time = default_end_time - default_start_time
            commandWait(device, timeout)
            device.command.stopRecording()
            commandWait(device, timeout)

            # Verify that the device's status is back to idle.
            assert (device.command.status[1] ==
                    endaq.device.DeviceStatusCode.IDLE), "Device is not idle."

            # Verify the wait=False case ran quicker than the wait=True case.
            print("false:", false_execution_time,
                  "true:", default_execution_time)
            assert (false_execution_time < default_execution_time
                    ), "Default returned quicker than when wait=False."


def test_start_recording_timeout(device_sn, setupTeardown):
    """ Tests that 'startRecording()' raises an Exception when 'timeout' is too low.

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    device = endaq.device.getDevices()[0]
    device.refresh()
    fw_version = device.firmwareVersion

    # Since startRecording's behavior is firmware specific, its tests are too!
    match fw_version:
        case a if 20000 <= a <= 20100:
            # Recordings can only be started, no status response. Command may be
            # unstable, fix is to unplug/replug USB
            assert False, "Firmware version not yet supported."
        case b if 20100 < b < 30000:
            # Recordings can only be started, no status response
            assert False, "Firmware version not yet supported."
        case c if 30000 <= c <= 30100:
            # Recordings can only be started, no status response
            assert False, "Firmware version not yet supported."
        case d if 30100 < d:
            # Recordings can be started, stopped, and device will send status
            # while recording

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
        case _:
            assert False, "Firmware version not supported."
