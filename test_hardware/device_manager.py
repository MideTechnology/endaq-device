from typing import Optional, Literal, Union, List, Dict, TYPE_CHECKING
import endaq.device
from endaq.device import DeviceStatusCode as Status
from test_hardware.helper_functions.general_config import GeneralConfig, GENERAL_CONFIG_IDS
from test_hardware.helper_functions.hardware_interface import (
    HardwareInterface, MockInterface,
    TTYInterface, RaspiInterface
)
import time
__all__ = ["DeviceManager", "safe_get_device"]
type interface_types = Union[Literal[0, "none"],
                             Literal[1, "tty"],
                             Literal[2, "raspi"]
                             ]
if TYPE_CHECKING:
    from ebmlite.core import MasterElement

class DeviceManager:
    """
    A class that is used to hold the testing device and perform common actions. 
    Note that while device is a mutable object, it is **not** a global object. 
    It is **highly** recommended to use `DeviceManager.device.xxxx` rather than 
    `device = DeviceManager.device; device.xxx`.

    Even if device manager is not used beyond the first device getter, it is
    still recommended to use this, as it is used for post-test teardown.

    Any errors raised from the device will be returned in their original form.
    """
    _device_sn: str
    _device: Optional[endaq.device.base.Recorder]
    init_conf: Optional["MasterElement"] 
    hw_interface: HardwareInterface

    def __init__(
            self, 
            device_sn: str, 
            interface_mode: interface_types, 
            get_on_init: bool = True
            ):
        self.device_sn = device_sn
        self.hw_interface = self._determine_hardware_interface(interface_mode)
        if get_on_init:
            self._device = safe_get_device(device_sn)
            self.init_conf = self._device.config.getConfig()
    
    def _determine_hardware_interface(self, interface_mode):
        if interface_mode == 0 or interface_mode == "none":
            return MockInterface()
        elif interface_mode == 1 or interface_mode == "tty":
            return TTYInterface()
        elif interface_mode == 2 or interface_mode == "raspi":
            return RaspiInterface()
        
        raise ValueError('interface_mode needs to be one of ("none", "tty", "raspi"), or (0,1,2), index respective')
        
        

    @property
    def device(self):
        if self._device is None:
            self._device = safe_get_device(self.device_sn, 30)
            self.init_conf = self._device.config.getConfig()
        return self._device

    @device.setter
    def device(self, device: endaq.device.base.Recorder):
        self.device_sn = device.serial
        self._device = device
        self.init_conf = device.config.getConfig()

    @property
    def device_sn(self):
        """
        A dedicated getter for device_sn, attempting to retrieve a serial number if one was not 
        provided.
        """
        if self._device_sn is None:
            if self._device is None:
                print('retreiving new device')
                devices = safe_get_device()
                if len(devices) == 0: return
                else:  
                    self._device_sn = devices[0].serial
                    self.device = devices[0]
            else:
                self._device_sn = self._device.serial
        return self._device_sn

    @device_sn.setter
    def device_sn(self, device_sn):
        """
        a dedicated setter for device_sn, additionally setting the device parameter
        to the device with this device serial number.
        """
        self._device_sn = device_sn
        self._device = safe_get_device(device_sn = device_sn)

    def dememomize_device(self):
        self._device = None
        self.init_conf = None

    def apply_conf(self, conf: Optional[Dict], revert_to_base: bool = True):
        """
        Intended to be used During test startup. For singular values, it is recommended to instead
        use `device.config.items[Foo].value = Bar`. It'll be marginally faster, but significantly
        easier to parse at a glance.

        :param conf: The values to change
        :param revert_to_base: If set to true, the default config will be used in conjunction
            with the set values in :param:`conf`. If set to False, only the items set in 
            :param:`conf` will be changed. 
            
        """
        if conf is None: conf = {}

        if revert_to_base:
            changes = GeneralConfig(**conf).set_configs(self.device)
        else:
            changes = len(conf) != 0
            for k, v in conf.items():
                self.device.items[GENERAL_CONFIG_IDS[k]].value = v

        if changes:
            self.device.config.applyConfig()
            if conf.get('WifiEnable', 0):
                self.device.command.awaitReconnect()
                self.device.command.reset()
                self.device.command.awaitReconnect()
        return changes
    
    def end_test(self, failed: bool):
        self.optional_stop()
        self.device.command.setTime() #time isn't part of config ids, need way of resetting it
        self.device.config.recordingDir = "RECORD" #recordingDir isn't part of the config ids
        if failed:
            return self._cleanup_failure()
        if self.device.config.getConfig() != self.init_conf:
            self.device.config.loadConfig(self.init_conf)
            self.device.config.applyConfig()
        #revert all triggers to be disabled.

    def _cleanup_failure(self):
        """a "private" helper to deal with test failures."""
        device = self.device
        if not device.command.awaitReconnect(timeout = 30):
            self.hw_interface.set_usb(True)
        
        self.optional_stop()

        #if config change, revert config
        if device.config.config != self.init_conf:
            device.config.loadConfig(device.config.config)
            device.config.applyConfig()
            self.device.command.reset()
        #hold button for 18 seconds.
            
    def end_session(self):
        """
        Note that this doesn't garbage collect the DeviceManager, as there is no way to delete
        oneself. Rather, this is a counterpart to :func:`end_test`, for when all pytest tests
        are finished.
        """
        device = self.device
        device.command.awaitReconnect(30) #ensure access to pings
        self.optional_stop()


    def start_recording(self, status: Union[Status, List[Status]] = Status.RECORDING):
        """
        Runs through the starting process of a device, using device.command.startRecording(),
        regardless of the hardware interface, and asserting that the right values are set.
        """
        self.device.command.startRecording()
        if isinstance(status, Status): status = [status]
        #assert wait_for_status(device, status)
        self.device.command.awaitReconnect(30)
        self.device.command.ping()
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
        if 20000 <= self.device.firmwareVersion <= 30100:
            #assert stopRecOldFW(device, is_raspi) is None
            if isinstance(self.hw_interface, MockInterface):
                assert self.hw_interface != MockInterface, "Recording can only be stopped with a " \
                "Interactively, through -s or --raspi."
            else:
                self.hw_interface.timed_button_press(0.5)
        else:
            self.device.command.awaitReconnect(timeout=30)
            assert self.device.command.stopRecording() is True, "Device did not stop recording."
        
        self.device.command.awaitRemount(timeout=30)
        self.device.command.awaitReconnect(timeout=30)
        self.device.command.ping()
        assert (self.device.command.status[1] == Status.IDLE or
            self.device.command.status[1] == Status.IDLE_UNMOUNTED), "Device is not idle."

    def optional_stop(self) -> bool:
        """
        Stops a recording iff it can. 

        :return: a boolean, True if the device is now in an idle state, and False
            if there was no way to tell if the device can be stopped.
        """
        #if we have a device, retreive it. if we don't, try to find one.
        device = self._device or safe_get_device(self.device_sn or "", unmounted=True)
        if device is None:
            return False
        if not device.command.awaitReconnect(timeout = 30):
            return False
        device.command.ping()
        if device.command.status[1] in [Status.RECORDING, Status.TRIGGERING]:
            self.stop_recording()
            return True
        return False
    
    def make_recording(
            self, 
            status: Union[Status, List[Status]] = Status.RECORDING,
            length: int = 5
            ):
        """
        Follows the same rules as start_recording and stop_recording.
        """
        self.start_recording(status)
        time.sleep(length)
        self.stop_recording()


def safe_get_device(device_sn: str="", timeout: int=15, unmounted=False) -> endaq.device.Recorder:
    """
    
    """
    # debugging the timeout
    out_of_time = False
    start_time = time.time()
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
    raise endaq.device.exceptions.CommunicationError(f"Could not find device {device_sn} in "\
                                                     f"{timeout} seconds. Attached Devices: {devices}")