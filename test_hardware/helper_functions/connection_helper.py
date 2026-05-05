import endaq.device
import time
import pytest

class ConnectionError(Exception):
    """
    An Error thrown by any function in `connection_helper.py`. This is used by
    the main test methods to determine if the error is communication based or 
    implementation based.
    """

"""
All functions should have a boolean parameter raise_on_failure with default of True
to dictate what happens on failure of a connection
"""

def get_status(device, raise_on_failure: bool = True) -> endaq.device.response_codes.DeviceStatusCode:
    try:
        resp = device.command.ping()
        print(f"Status code: {device.command.status=}")
    except Exception as e:
        print(f"get_status got error {e}")
        if raise_on_failure: raise ConnectionError(f"get_status raised error {e}")
        return None
    return device.command.status[1]


# Helper functions and fixtures:
def commandWait(device, timeout, raise_on_failure: bool = True):
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
    if raise_on_failure: raise ConnectionError("CommandWait timed out before device reconnected")


def wait_for_status(
        device: endaq.device.Recorder, 
        target_status: list[endaq.device.response_codes.DeviceStatusCode], 
        timeout: int=15,
        raise_on_failure: bool = True) -> bool:
    """
    Makes multiple attempts to get the status of the device, repeating
    until either the correct status is found or timeout is reached.

    :param device: The recorder to ping
    :param target_status: the list of status to wait for.
    :param timeout: Number of seconds before this stops looking for the target status.
    :param raise_on_failure: sets if a `ConnectionError` should be raised 
    """
    # Debugging the timeout
    out_of_time = False
    start_time = time.time()
    status = "Not Yet Set"
    while not out_of_time:
        status = get_status(device)
        if status in target_status:
            print(f"Got status {status} after {time.time()-start_time:0.2f} sec")
            return True
        if time.time() - start_time > timeout:
            out_of_time = True
        else:
            time.sleep(1)
    msg = f"Did not get status {target_status} after {timeout} sec. Stuck in {str(status)}"
    
    if raise_on_failure:
        raise ConnectionError(msg)
    
    print(msg)
    return False


#no raise_on_failure parameter as it always will raise.
def safe_get_device(device_sn: str="", timeout: int=15, unmounted=False) -> endaq.device.Recorder:
    """
    
    """
    # debugging the timeout
    out_of_time = False
    start_time = time.time()
    time.sleep(1)
    while not out_of_time:
        if time.time() - start_time > timeout:
            out_of_time = True
        devices = endaq.device.getDevices(unmounted=unmounted)
        if len(devices) == 0:
            continue
        for dev in devices:
            if not device_sn or dev.serial.lower() == device_sn.lower():
                print(f"Connected after {time.time() - start_time}")
                return dev
        if not out_of_time:
            time.sleep(1)
    devices = endaq.device.getDevices()
    raise endaq.device.exceptions.CommunicationError(f"Could not find device {device_sn} in {timeout} seconds. Attached Devices: {devices}")

def safe_ping(device, to_ping = "", timeout: int=15, raise_on_failure: bool = True):
    """
    safe pings the device by waiting 
    :param timeout: a non-positive timeout will result in an infinite timeout
    :return: the returned ping information
    """
    out_of_time = False
    start_time = time.time()
    time.sleep(1)
    while not out_of_time:
        if time.time() - start_time > timeout:
            out_of_time = (timeout > 0)
        if not out_of_time:
            time.sleep(1)
        try: 
            info = device.command.ping(to_ping)
            return info
        except Exception as ex:
            pass
        device.command.ping(to_ping)
    

#raise_on_failure not needed, will be raised if not is_raspi
def stopRecOldFW(device, is_raspi):
    """ On an ALREADY RECORDING device with FW <= 3.01.00, check that running
        'stopRecording()' raises an exception and then use a simulated button
        press (ONLY WORKS ON RASPI) to stop the recording.

        :param device: Connected device.
    """
    if is_raspi is False:
        raise ConnectionError("stopRecOldFW Can't run test on old firmware unless it's connected to a RasPi setup.")

    # Attempt to run stop recording and catch the thrown exception
    commandWait(device, 5)
    with pytest.raises(endaq.device.exceptions.CommandError) as exc_info:
        device.command.stopRecording()

    # Simulated button press to stop recording
    timed_button_press(1)

    # Check the device with old FW raised an exception
    assert (exc_info.type == endaq.device.exceptions.CommandError
            ), "Old FW didn't error out on stopRecording."
