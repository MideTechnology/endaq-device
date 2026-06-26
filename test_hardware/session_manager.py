from typing import Optional, Literal, Union, List, Tuple, Any, Callable
from test_hardware.connection_manager import (
    ConnectionManager, SerialConnectionManager, WifiConnectionManager,
    safe_get_device, safe_get_wifi_device, SessionStateError
)
import time
import uuid
import endaq.device
from endaq.device import DeviceStatusCode as Status
from endaq.device import Recorder
from ebmlite.core import MasterElement
from endaq.device.mqtt import MQTTConnector
from test_hardware.helper_functions.hardware_interface import (
    HardwareInterface, MockInterface,
    TTYInterface, RaspiInterface, NoInteractInterface
)
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import glob
import subprocess
import platform
import logging


__all__ = ["SessionManager"]
type interface_types = Union[Literal[0, "none"],
                             Literal[1, "tty"],
                             Literal[2, "raspi"]
                             ]



class SessionManager:
    """
    A class that is used to hold the testing device and perform common actions. 
    Note that while device is a mutable object, it is **not** a global object. 
    It is **highly** recommended to use `SessionManager.device.xxxx` rather than 
    `device = SessionManager.device; device.xxx`.

    Even if device manager is not used beyond the first device getter, it is
    still recommended to use this, as it is used for post-test teardown.
    
    Any errors caused by the SessionManager will return a SessionStateError.
    Any errors raised from the device will be returned in their original form.
    """
    _hw_interface: HardwareInterface
    _all_connection_managers: ConnectionManager
    _connected_to: str

    def __init__(
            self, 
            device_sn: str, 
            interface_mode: interface_types, 
            ):
        self.device_sn = device_sn
        self._hw_interface = self._determine_hardware_interface(interface_mode)
        session_prefix = uuid.uuid4().hex[:5] #set to 5 for readability
        self._all_connection_managers = {
                "serial": SerialConnectionManager(device_sn, session_prefix, self._hw_interface), 
                "wifi": WifiConnectionManager(device_sn, session_prefix, self._hw_interface)
                }
        device, conn_type = _get_init_device(device_sn, None, 30)
        self._connected_to = conn_type
        self.connection_manager.enter(device)


    def _determine_hardware_interface(self, interface_mode):
        if interface_mode == 0 or interface_mode == "none":
            return NoInteractInterface(SessionStateError)
        elif interface_mode == 1 or interface_mode == "tty":
            return TTYInterface()
        elif interface_mode == 2 or interface_mode == "raspi":
            return RaspiInterface()
        
        raise SessionStateError(
            'interface_mode needs to be one of ("none", "tty", "raspi")'
            ', or (0,1,2), index respective')


    @property
    def device(self) -> Recorder:
        return self.connection_manager.device
    
    @device.setter
    def device(self, device):
        self.connection_manager.device = device

    @property
    def connection_manager(self) -> ConnectionManager:
        """
        Accesses the SessionManager's ConnectionManager, which controls the 
        device and how it is interacted with
        """
        return self._all_connection_managers[self._connected_to]
    
    @property
    def hw_interface(self) -> HardwareInterface:
        return self._hw_interface

    @property
    def idle_statuses(self) -> List[Status]:
        """
        The statuses that a device can be in while idle.
        Note that this is dependent on device connection
        """
        return self.connection_manager.idle_statuses

    @property
    def recording_statuses(self) -> List[Status]:
        """
        The statuses that a device can be in while recording.
        Note that this is dependent on deivce connection
        """
        return self.connection_manager.recording_statuses

    @property
    def recording_directory(self) -> str:
        """
        The recording directory where the files are stored.
        """ 
        return self.connection_manager.recording_dir       

    def dememoize_device(self):
        """
        dememoizes the device attached with this session, forcing
        it to be refound upon next device getter call.
        """
        self.connection_manager.dememoize_device()
        
    def end_test(self, failed: bool):
        device = self.device
        device.command.awaitReconnect(timeout=30)
        self.optional_stop()
        if failed:
            return self._cleanup_failure()
        self.connection_manager.revert_to_base()

    def _cleanup_failure(self):
        """
        a "private" helper to deal with test failures. This **will** cleanup, 
        and if impossible will raise an error.

        :raise SessionStateError: if it is in some way impossible to cleanup
            (e.g, unable to connnect to device, unable to stop)
        """
        device = self.device
        try:
            device.command.awaitReconnect(timeout = 30)
        except:
            self.hw_interface.set_usb(True)
        
        if not self.optional_stop():
            raise SessionStateError("unable to stop the device's recording")

        self.connection_manager.revert_to_base()  

    def end_session(self):
        """
        Performs actions that happens after all tests have been ran.
        Note that this doesn't garbage collect the SessionManager, as there is no way to delete
        oneself. Rather, this is a counterpart to :func:`end_test`, for when all pytest tests
        are finished.
        """
        """
        device = self.device
        device.command.awaitReconnect(30) #ensure access to pings
        self.optional_stop()
        """
    #=== RECORDING HELPERS ===#

    def start_recording(self):
        """
        Runs through the starting process of a device, using device.command.startRecording(),
        regardless of the hardware interface, and asserting that the right values are set.
        """
        self.device.command.startRecording()
        self.device.command.awaitReconnect(30)
        self.device.command.ping()
        status = self.recording_statuses
        assert (self.device.command.status[1] in status
                ), f"Expected status {status}, received {self.device.command.status[1]}"
        return self.device
    
    def stop_recording(self):
        """
        Runs through the processing of stopping a device recording. Defaults to device.command.stopRecording(), 
        but will refer to the hardware interface if the device's firmware is too low. 
        An AssertionError is raised if a Mock Interface is passed in. 
        """ 
        # Confirm device stopped recording
        device = self.device
        if 20000 <= self.device.firmwareVersion <= 30100:
            if isinstance(self._hw_interface, MockInterface):
                raise SessionStateError(
                        "Recording can only be stopped with interactively, through -s or --raspi."
                )
            else:
                self._hw_interface.timed_button_press(0.5)
        else:
            device.command.awaitReconnect(timeout=30)
            assert device.command.stopRecording() is True, "Device did not stop recording."
        
        device.command.awaitReconnect(timeout=60)
        device.command.ping()
        assert self.idle_statuses, "Device is not idle."

    def optional_stop(self) -> bool:
        """
        Stops a recording iff it can. 

        :return: a boolean, True if the device is now in an idle state, and False
            if there was no way to tell if the device can be stopped.
        """
        #if we have a device, retreive it. if we don't, try to find one.
        device = self.device
        if device is None:
            return False
        try:
            device.command.awaitReconnect(timeout = 30)
        except:
            return False
        device.command.ping()
        if device.command.status[1] in self.recording_statuses:
            self.stop_recording()
            device.command.awaitReconnect(timeout = 30)
            device.command.ping()
        return device.command.status[1] in self.idle_statuses
    
    def make_recording(
            self, 
            length: int = 5
            ) -> Path:
        """
        Follows the same rules as start_recording and stop_recording. 
        And returns a path to the recording.

        :return: a Path with the location of the newest recording
        """
        self.start_recording()
        if self.device.command.canStream:
            self.device.command.saveStream(self.recording_directory)

        time.sleep(length)

        if self.device.command.canStream: 
            self.device.command.closeStream()
        self.stop_recording()
        return self.get_newest_rec()

    def get_newest_rec(self) -> Optional[Path]:
        """
        newest is **not** dictated by timestamp, as that is relevant on system time, which can 
        be changed. Instead, we get the prefix, then find the recording with the latest number
        attached to it.
        """
        directory = self.recording_directory
        prefix = self.device.config.items[0x15ff7f].value
        prefixed_files = glob.glob(str(directory / f"{prefix or ""}*"))
        if prefixed_files == []:
            raise SessionStateError(f"unable to find any files that match the prefix"
                                    f"{prefix} and recording directory {directory}") 
        latest = max(prefixed_files) if prefixed_files is not [] else None
        return latest
    
    def toggle_connection(self, connect_to: str):
        """
        changes the connection method to the given value.

        :param connect_to: the connection method to toggle to. 
            In the current implementation, it can be one of  `serial` or `wifi`.
        
        :return: None
        """
        if self._connected_to == connect_to:
            return
        try:
            previous_device = self.device
        except:
            self.connection_manager.memoize()
            previous_device = self.device
        self.connection_manager.exit()
        self._connected_to = connect_to
        self.connection_manager.enter(previous_device)


def valid_sn(device_sn: Union[str, int]) -> bool:
    """
    Determines if the given serial-number like value is valid.

    :param device_sn: the serial number to check, either formated 
        as [S|H|W]XXXXXXX (str) or XXXX (int)
    
    :return: boolean representing if the serial number is valid
    """
    #FUTURE: This will have to be updated as we release new "series" of products
    if isinstance(device_sn, str):
        if device_sn[0] in 'SHW':
            if 2000 <= int(device_sn[1:]) <= 30000:
                return True
    else:
        if 2000 <= device_sn <= 30000:
            return True

    return False

def _get_init_device(
        device_sn: str,
        mqtt: Union[bool, ...],
        individual_timeout: int, 
        ) -> tuple[Recorder, str]:
    """
    Finds a device through any means available. This method should not have 
    to be used beyond session instantiation
    
    :param device_sn: 
        an empty string matches against any device, and returns the first one found
    :param mqtt: a boolean value of False skips mqtt. If provided a ..., a new one will not
        be instantiated. A value of True isntantiates a ... and connects it
    :param individual_timeout: in seconds, the timeout for each way of getting a device
        any non-positive will be snapped to 60 seconds, otherwise not all search methods
        will be used

    :return: a tuple of (device_found, connection_type that found it)   

    :raise SessionStateError: if a device was unable to be found through any means
    """
    #TODO
    get_methods = [("serial", safe_get_device)]
    if mqtt is not None:
        get_methods.append((
            "wifi",
            lambda device_sn, timeout: safe_get_wifi_device(mqtt, device_sn, timeout)
            ))
    for conn_type, getter in get_methods:
        try:
            device = getter(device_sn=device_sn, timeout=individual_timeout)
            return device, conn_type
        except:
            continue
    raise SessionStateError(f"A device was unable to be found through {list(map(lambda x: x[0], get_methods))}")

