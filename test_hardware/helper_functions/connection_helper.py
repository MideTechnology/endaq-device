import endaq.device
import time
import pytest
 

def get_status(device) -> endaq.device.response_codes.DeviceStatusCode:
    try:
        resp = device.command.ping()
        print(f"Status code: {device.command.status=}")
    except Exception as e:
        print(f"get_status got error {e}")
        return None
    return device.command.status[1]


# Helper functions and fixtures:
def commandWait(device, timeout):
    """ Wait for the device to reconnect after a command is sent.

        :param device: Connected device.
        :param timeout: Time (seconds) to wait for the device to reconnect.
    """

    for _ in range(int(timeout)):
        try:
            resp = device.command.ping()
            print(f"Status code: {device.command.status=}\t")
            if device.command.status[1] == endaq.device.response_codes.DeviceStatusCode.RECORDING or \
                    device.command.status[1] == endaq.device.response_codes.DeviceStatusCode.IDLE_UNMOUNTED:
                print(
                    f"Device is recording. Status code: {device.command.status[1]}")

        except Exception as e:
            print(f"Got error {e}")

        # Getting here means that either expected_path is none and devices still
        # connected or the specific device path has not left yet
        time.sleep(1)


def wait_for_status(device: endaq.device.Recorder, target_status: list[endaq.device.response_codes.DeviceStatusCode], timeout: int=15) -> bool:
    # Debugging the timeout
    out_of_time = False
    start_time = time.time()
    while not out_of_time:
        status = get_status(device)
        if status in target_status:
            print(f"Got status {status} after {time.time()-start_time:0.2f} sec")
            return True
        if time.time() - start_time > timeout:
            out_of_time = True
        else:
            time.sleep(1)
    print(f"Did not get status {target_status} after {timeout} sec")
    return False


def safe_get_device(device_sn: str="", timeout: int=15, unmounted=False) -> endaq.device.Recorder:
    """
    
    """
    # debugging the timeout
    out_of_time = False
    start_time = time.time()
    while not out_of_time:
        devices = endaq.device.getDevices(unmounted=unmounted)
        if len(devices) == 0:
            continue
        for dev in devices:
            if not device_sn or dev.serial.lower() == device_sn.lower():
                print(f"Connected after {time.time() - start_time}")
                return dev
        if time.time() - start_time > timeout:
            out_of_time = True
        else:
            time.sleep(1)
    devices = endaq.device.getDevices(unmounted=unmounted)
    raise endaq.device.exceptions.DeviceError(f"Could not find device {device_sn} in {timeout} seconds. Attached Devices: {devices}")


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
