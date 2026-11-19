from typing import Optional, List, override, Callable
import logging
from pathlib import Path
import tempfile
from test_hardware.helper_functions.general_config import (
        revert_to_base, equal_cfg, create_serial_config, create_wifi_config
)
import time
import os
import contextlib
from abc import ABC, abstractproperty, abstractmethod
import copy
from ebmlite.core import MasterElement
from test_hardware.helper_functions.hardware_interface import (
    HardwareInterface, MockInterface,
    TTYInterface, RaspiInterface, NoInteractInterface
)
from endaq.device import Recorder, DeviceStatusCode as Status
from endaq.device.mqtt.mqtt_interface import MQTTConnector
from endaq.device.mqtt.manager import start
from endaq.device.util import getMyIP
import endaq.device


__ALL__ = ["ConnectionManager", "SerialConnectionManager", "WifiConnectionManager"
           "safe_get_device", "safe_get_wifi_device", "SessionStateError",
           "safe_apply_config"]

class SessionStateError(AssertionError):
    """
    An exception used for any Errors that arise from malformed state information,
    that is not a result of the test itself.

    As an example, trying to access mosquitto information for a non-MQTT device is
    a `SessionStateError`, while a device timing out during config application is not.
    """
    pass

class ConnectionManager(ABC):
    """
    A manager class that deals with connection to the device.
    This ABC exists as a way of type checking, and a few universal instantiation methods.
    Methods are dependent to the purpose of the ConnectionManager, and is not 
    guarenteed to be implemented in every instance.
    """
    
    @abstractmethod
    def enter(
            self,
            device: Recorder,
            no_togggle: bool = False
            ) -> None:
        """
        (Re-)Enters the ConnectionManager, setting the device back up with the desired
        connection and any config / other info that needs to be adjusted.
        This should be called whenever switching (back) to this ConnectionManager.

        :param device: the recorder to associate with this ConnectionManager. It will then be 
            properly confiugred to the associated device.
        :param no_toggle: True implies there is no need to toggle to the device, as it already connected
            to the managers specifications. session instantiation aside, there should almost never be a reason 
            for no_toggle to be True.
        """
        pass

    @abstractmethod
    def exit(self) -> None:
        """
        Exits the Connection Manager. Used to guarentee that the ConnectionManager is not
        open from a previous iteration, containing information that is no longer valid.
        """
        pass 

    @abstractmethod
    def revert_to_base(self) -> bool:
        """
        Reverts the device associated with the connection manager to it's base config,
        which is consistent to it's manager
        
        :return: boolean stating if the config needed to change
        """
        pass

    @abstractmethod
    def dememoize(self) -> None:
        """
        demomizes the device attached to the ConnectionManager,
        forcing the device to be searched for before next retreival
        """
        pass

    @abstractmethod
    def memoize(self) -> None:
        """
        This only needs to be called after `self.dememoize`, and is not needed
        after enter()
        """
        pass

    #===== PROPERTIES =====#
    @abstractproperty
    def device_sn(self) -> str:
        """
        The serial number of the device attached to this connection manager
        """
        pass

    @abstractproperty
    def device(self) -> Recorder:
        """
        The Recorder that is attached to this connection manager by
        its specified connection type

        :raise SessionStateError: if the device was not previously 
            established when entering 
        """
        pass
    
    @abstractproperty
    def recording_dir(self) -> Path:
        """
        the directory where all recordings **made from this session** are stored

        :raise SessionStateError: if the recording directory was not 
            established when entering
        """
        pass

    @abstractproperty
    def idle_statuses(self) -> List[Status]: 
        """
        The statuses this device could be in when not performing any
        actions
        """
        pass
    
    @abstractproperty
    def recording_statuses(self) -> List[Status]:
        """
        The statuses this device could be in when recording data
        """
        pass

    @abstractproperty
    def connection_type(self) -> str:
        """
        A string representation of how the device is connected to
        the ConnectionManager.
        """
        pass



class SerialConnectionManager(ConnectionManager):
    _device_sn: str = None
    _device: Optional[Recorder]
    _recording_dir: Path
    _base_config: MasterElement
    _hw_interface: HardwareInterface

    def __init__(self, device_sn: str, uuid: str, hw_interface: HardwareInterface):
        self._device_sn = device_sn
        self._base_config = create_serial_config(uuid)
        self._hw_interface = hw_interface 
        self._device = None

    @override
    def enter(self, device, no_toggle: bool = False) -> None:
        device_sn = device.serial
        safe_apply_config(device, self._base_config)
        self._recording_dir = Path(device.path) / Path(
            r"DATA/" + (device.config.recordingDir or r"RECORD/") 
        )
        self._device_sn = self.device_sn
        if no_toggle:
            self._device = device 
            self.device.awaitReconnect(timeout=30)
        else:
            self._hw_interface.set_usb(True)
            device = safe_get_device(device_sn, timeout=30) 
            self._device = device
            self.revert_to_base()
        self._device.command.awaitReconnect()

    @override
    def exit(self) -> None:
        self._device = None

    @property
    def device_sn(self) -> str:
        return self._device_sn

    @device_sn.setter
    def device_sn(self, device_sn):
        self._device_sn = device_sn
        self._device = safe_get_device(device_sn)
    
    @property
    def device(self) -> Recorder:
        if self._device is None:
            raise SessionStateError("Attempted to access `device` property before entering manager")
        return self._device
        
    @device.setter
    def device(self, device):
        self._device = device
        self._device_sn = device.serial
    
    @property
    def recording_dir(self): 
        if self._recording_dir is None:
            raise SessionStateError("enter() wasn't called when switching to SerialConnectionManager")
        return self._recording_dir

    @property
    def idle_statuses(self) -> List[Status]:
        return copy.copy([Status.IDLE])

    @property
    def recording_statuses(self) -> List[Status]:
        return copy.copy([Status.RECORDING])

    @property
    def connection_type(self) -> str:
        return "serial"

    @override
    def dememoize(self):
        self._device = None

    @override
    def memoize(self):
        device = safe_get_device(self.device_sn, timeout=30) 
        self._device = device
        self.revert_to_base()
    
    @override
    def revert_to_base(self): 
        device = self.device
        device.config.loadConfig()
        d_cfg = device.config.config
        if not equal_cfg(d_cfg, self._base_config):
            safe_apply_config(device, self._base_config, 60)

class WifiConnectionManager(ConnectionManager):
    """
    A ConnectionManager for WiFi over MQTT. 
    Note that this does not start the mosquitto server, and that nothing is started
    until enter is called.
    """

    _device_sn: str
    _device: Recorder
    _recording_dir: Path
    _base_config: MasterElement 
    _mqtt_connector: MQTTConnector
    _hw_interface: HardwareInterface
    _first_enter: bool

    def __init__(self, device_sn: str, session_prefix: str, hw_interface):
        self._device_sn = device_sn
        self._prefix = session_prefix
        self._device = None #wait for enter
        self._mqtt_connector = None
        self._recording_dir = None
        self._hw_interface = hw_interface
        self._first_enter = True

    @override
    def enter(self, device, no_toggle = False) -> None:
        print('entering wifi connection manager')
        if self._first_enter:
            start(background=True, name=self._prefix)
            self._first_enter = False
            """
            HACK: In order to not drown out pytest outputs, we silence the loggging and send it to a file.
                  However, due to the nature of logging, we have to silence logging at the **root** level.
            """
            logging.root.handlers.clear()
            mqtt_logger = logging.getLogger("endaq.device.mqtt")
            mqtt_logger.addHandler(logging.FileHandler("./log_out.txt", "w"))


        ip_addr = getMyIP() 
        self._base_config = create_wifi_config(self._prefix, ip_addr) 
        if self._mqtt_connector is None:
            print('getting MQTTConnector')
            #Using wildcard seems more consistent, the prefix is unique enough that it 
            #should never be an issue
            self._mqtt_connector = MQTTConnector().find(self._prefix)

        if self._recording_dir is None:
            #let program close garbage collect it
            self._recording_dir = tempfile.TemporaryDirectory()

        if no_toggle:
            try:
                self._device = safe_get_wifi_device(self._mqtt_connector, self._device_sn, 60)
            except:
                raise SessionStateError(
                        f"Attempted and failed to get device {device} without toggling"
                        )
            return
        print("applying config")
        safe_apply_config(device, self._base_config)
        device.command.awaitReconnect()
        device.command.setAP(ssid="Mide-LinuxNet", password=os.environ['LinuxNetPWD']) 
        print("getting wifi device")
        self._device = safe_get_wifi_device(self._mqtt_connector, self._device_sn, 60)

    @override
    def exit(self) -> None:
        self._device = None

    @override
    def dememoize(self) -> None:
        self._device = None
    
    @override
    def memoize(self) -> None:
        self._device = safe_get_wifi_device(self._mqtt_connector, self._device_sn, 60)

    @property
    def device_sn(self) -> str:
        return self.device_sn
    
    @device_sn.setter
    def device_sn(self, device_sn):
        self._device_sn = device_sn
        self._device = safe_get_wifi_device(self._mqtt_connector, device_sn)
    
    @property
    def device(self) -> Recorder:
        if self._device is None:
            self._device = safe_get_wifi_device(self._mqtt_connector, self._device_sn)
        return self._device
    
    @property
    def recording_dir(self) -> Path:
        if self._recording_dir is None:
            raise SessionStateError("WifiConnectionManager's recording_dir was accessed"
                                    "before calling enter()")
        return self._recording_dir
    
    @property
    def mqtt_connector(self):
        if self._mqtt_connector is None:
            raise SessionStateError("WifiConnectionManager's mqtt_connector was accessed"
                                    "before calling enter()")
        return self._mqtt_connector

    @property
    def idle_statuses(self) -> List[Status]:
        return copy.copy([Status.IDLE, Status.SLEEPING, Status.IDLE_UNMOUNTED]) #TODO: confirm

    @property
    def recording_statuses(self) -> List[Status]:
        return copy.copy([Status.STREAMING, Status.RECORDING])
    
    @property
    def connection_type(self) -> str:
        return "wifi"

    @override
    def revert_to_base(self): 
        device = self.device
        device.command.setLockID(device.command.getLockID())
        device.command.clearLockID(device.command.getLockID())
        device.config.loadConfig()
        d_cfg = device.config.config
        if not equal_cfg(d_cfg, self._base_config):
            safe_apply_config(device, self._base_config, 60)

#===== Connection helpers / Errors =====#

def safe_get_device(device_sn: str="", timeout: int=15, unmounted=False) -> Recorder:
    """
    Attempts to find either a specific or any serial device by seraching multiple times,
    in case unsuccessful the first time(s)

    :return: a Recorder with the given serial number (if provided)
    
    :raise SessionStateError: if a device of `device_sn` was not found within `timeout` seconds
    """
    # debugging the timeout
    dev = _safe_get_device(
        device_sn, 
        timeout, 
        lambda: endaq.device.getDevices(unmounted=unmounted)
        )
    if dev is not None:
        return dev
    devices = endaq.device.getDevices()
    raise SessionStateError(
        f"Could not find device {device_sn} in {timeout} seconds."
        f"Attached Devices: {devices}"
        )

def safe_get_wifi_device(
        mqtt_connector: MQTTConnector,
        device_sn: str="",
        timeout: int = 30,
):
    """ 
    Attempts to find either a specific or any wifi device by querying multiple times, 
    in case it was unsucessful the first time(s)

    :param mqtt_connector: the MQTTConnector to find the devices with. 
    :param device_sn: the device TODO
    :param timeout: 

    :raise SessionStateError: if a device of `device_sn` was not found within `timeout` seconds
    """
    dev = _safe_get_device(
        device_sn,
        timeout,
        lambda: mqtt_connector.getDevices()
    )
    if dev is not None:
        return dev

    raise SessionStateError(f"unable to find {device_sn} in {timeout} seconds through"
                            f"the MQTT broker")
def _safe_get_device(
        device_sn: str,
        timeout: int,
        device_getter: Callable[[], List[Recorder]],
) -> Optional[Recorder]:
    """
    Abstracted work for safe_get_device like functions, searching for a device
    for `timeout` seconds in case it didn't connect on first attempt

    :param device_sn: . An empty-string value will search for all devices, and returns
        the first one found.
    :param device_getter: a lambda that searches for devices with no parameters. 
        eg (lambda: endaq.device.getDevices())
    :param timeout: 
        a non-positive time will result in searching indefinetly.

    :return: None if a device is not found, otherwise, the device
    """

    start_time = time.time()
    search_inf = not device_sn or timeout <= 0

    while search_inf or time.time() - start_time < timeout:
         devices = device_getter()
         for dev in devices:
            if not device_sn or dev.serial.lower() == device_sn.lower():
                print(f"Connected after {time.time() - start_time}")
                return dev
    return None

def safe_apply_config(
        device: Recorder,
        cfg: Optional[MasterElement],
        timeout: int = 30
        ) -> bool:
    """
    A helper function to gaurentee that a config is applied, that is used to work around a bug.
    Note that this function will print whenever the changes do not apply. 

    :param device: the device to apply the config to.
    :param cfg: The config to apply to the device. 
        A value of none will apply the config that is on the device by default
    :param timeout: The number of seconds to attempt to populate the config info. 
        a non-positive integer will result in attempting an infinite number of times

    :return: a boolean dictating if the config was applied
    """
    device.config.loadConfig(cfg)
    device.config.applyConfig()
    device.command.reset()
    time.sleep(5)
    device.command.awaitReconnect(timeout=30)
    loop_inf = (timeout <= 0)
    start_time = time.time()
    while loop_inf or time.time() - start_time < timeout:
        device.config.loadConfig()
        attr_vals = [getattr(device, attr, False) for attr in ["name", "notes", "recordingDir"]]
        if None not in attr_vals:
            device.refresh()
            device.command.reset()
            time.sleep(5)
            device.command.awaitReconnect(timeout=30)
            return True
        print("config attributes not populated, trying again")
    return False
