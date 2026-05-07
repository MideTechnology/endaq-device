"""
Common subtasks that are used in device tests
"""
from test_hardware.helper_functions.connection_helper import safe_get_device, wait_for_status
from endaq.device import DeviceStatusCode as Status
import time

def config_name_from_id(device, config_id):
    pass

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

def make_recording(device, device_sn, start_status, is_raspi, rec_length = 5):
    """
    Simulates the process of recording, starting, waiting, then stopping.

    :param rec_length: 
        Note that this will only guarentee the minimum recording length, not the total
        recording length, as starting / stopping recording takes time.
    """
    device = start_recording(device, device_sn, start_status)
    time.sleep(rec_length)
    device = stop_recording(device, device_sn, is_raspi)