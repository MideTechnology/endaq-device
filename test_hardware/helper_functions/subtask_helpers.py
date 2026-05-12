"""
Common subtasks that are used in device tests
"""
from test_hardware.helper_functions.connection_helper import safe_get_device, wait_for_status, stopRecOldFW
from typing import Union, List, Any, Optional
from endaq.device.base import Recorder
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

def setup_cfgs(device_getter: Union[Recorder, str], 
                  cfg_ids: Union[int, List[int]], 
                  cfg_vals = Union[Any, List[Any]],
                  raise_on_failure: bool = True
                 ) -> Optional[Recorder]:
    """

    There should be an equal number of `cfg_ids` and `cfg_vals`. 
    
    :param device_getter: The way of . If an string is passed through, it will be used with `safe_get_device`
        to retreive the device. if Recorder is used, that Recorder will be used.
    :param cfg_ids: One or more config ids found in , that are respective to values in `cfg_vals`
    :param cfg_vals: One or more config values, being mapped to the respective id in `cfg_ids`
    :param raise_on_failure: sets the behavior when an invalid cfg_id or invalid cfg_val is given. If set to
        true, a ValueError will be raise. If set to False, the Recorder with no changed config values will be returned.
    
    :return : a Recorder with the applied config settings. This helper function **does not** wait 
    for the device to be reconnected.
    """
    try:
        device = None
        if isinstance(device_getter, Recorder): 
            device = device_getter
        else:
            device = safe_get_device(device_getter)
            
        if not isinstance(cfg_ids, List): cfg_ids = [cfg_ids]
        if not isinstance(cfg_vals, List): cfg_vals = [cfg_vals]
            
        for k, v in zip(cfg_ids, cfg_vals):
            device.config.items[k].value = v
        device.config.applyConfig()
        return device
    except Exception as exc:
        if raise_on_failure:
            _setup_handle_failure(exc, device)
        else: 
            if device is not None:
                device.config.revert()
            return device

def _setup_handle_failure(exc, device):
    """
    helper to deal with setup_cfgs(raise_on_failure = True), 
    abstracted out for readability.
    """
    #TODO: implement _setup_handle_failure
    pass