"""
Contains fixtures used in device tests. Note that some fixtures are in `conftest.py`
"""
from test_hardware.conftest import is_raspi, device_sn
from test_hardware.device_manager import DeviceManager, safe_get_device
import pytest
import sys
from test_hardware.helper_functions.hardware_interface import *
from test_hardware.helper_functions.connection_helper import safe_get_device, get_status
from test_hardware.helper_functions.general_config import GeneralConfig
import endaq.device
from endaq.device import DeviceStatusCode as Status

__ALL__ = ["noSkipHardwareInterface", "setupTeardownSession", "setupTeardown", "newDir"]

@pytest.fixture(scope="session", autouse=True)
def hardwareCreation(is_raspi):
    if is_raspi:
        print(f"Setting Raspi interface")
        hw = RaspiInterface()
    else:
        if not sys.stdin.isatty():
            hw = MockInterface()
        else:
            hw = TTYInterface()
    yield hw

#====   ===#
@pytest.fixture
def hardwareInterface(hardwareCreation):
    if isinstance(hardwareCreation, MockInterface):
        pytest.skip("Skipping interactive test in non-interactive mode. Run pytest with -s option")
    yield hardwareCreation

@pytest.fixture(scope="session")
def noSkipHardwareInterface(hardwareCreation):
    yield hardwareCreation
#===   ===#

@pytest.fixture(scope="session", autouse=True)
def device_manager(device_sn, is_raspi):
    yield DeviceManager(
        device_sn = device_sn, 
        interface_mode = 2 if is_raspi else 1 if sys.stdin.isatty() else 0,
        get_on_init=True
        )


@pytest.fixture(scope="session", autouse=True)
def setupTeardownSession(device_manager, noSkipHardwareInterface):
    """ Set up and teardown GPIO RasPi controls at the beginning and end
        of a session.

        :param is_raspi: True if the tests are meant to run on a RaspberryPi,
            False otherwise. Set in command line.
    """
    # Put the device in default configuration
    print(f"Setting up session")
    config_dict = {"WifiEnable": 0, "PreRecordingDelay": 0, "RecordingTimeLimit": 120}
    device = device_manager.device 
    config = GeneralConfig(**config_dict)
    if config.set_configs(device, quick_config=True):
        print(f"Applying updated config")
        device.config.applyConfig()
        device.command.reset()  # Need to reset the device to turn the wifi on
        device = safe_get_device(timeout=30) # Wait for device to come back

    # Always update the device configuration
    print("\nSetting up RasPi...")
    noSkipHardwareInterface.set_usb(True)
    noSkipHardwareInterface.set_button(False)

    yield

    print("\nTearing down RasPi setup...")
    noSkipHardwareInterface.set_usb(True)
    noSkipHardwareInterface.set_button(False)

    device_manager.end_session()
    print("\nDone with RasPi tear down.")

    print(f"Finished session")

@pytest.fixture # with a default scope of "function"
def setupTeardown(noSkipHardwareInterface, device_sn):
    """ Hard reset the enDAQ before and after every test, and load in the configuration.

        :param is_raspi: True if the tests are meant to run on a Raspberry Pi,
            False otherwise. Set in command line.
        :param device_sn: the tested device's serial number collected from the 
            command line.
    """
    print(f"Setting up test")
    # Setup
    # start up and connect
    print("\nSetting up...")
    start_time = time.time()
    noSkipHardwareInterface.set_usb(True)
    # Hold the button down to reset the device
    noSkipHardwareInterface.timed_button_press(18)
    # Connect to the device
    device = safe_get_device(device_sn, timeout=30, unmounted=False)
    # Set it to standard configuration
    config_dict = {"WifiEnable": 0, "PreRecordingDelay": 0, "RecordingTimeLimit": 120}
    config = GeneralConfig(**config_dict)
    if config.set_configs(device, quick_config=True):
        print(f"Applying config")
        device.config.applyConfig()
        time.sleep(5)               # Is the config not written fast enough or something?
        device.command.reset()      # Need to reset the device to turn the wifi on
        device = safe_get_device(device_sn, timeout=30, unmounted=False)

    yield # Runs test

    # Teardown
    noSkipHardwareInterface.set_usb(True)
    noSkipHardwareInterface.set_button(False)
    

    print(f"Test completed after {time.time() - start_time} seconds.")
    print(f"Test Done")

@pytest.fixture
def triggerCleanup(noSkipHardwareInterface, device_sn):
    yield
    device = safe_get_device(device_sn, timeout=30, unmounted=True) #we are fine with unmounted devices
    try:
        device.command.stopRecording()
    except:
        noSkipHardwareInterface.timed_button_press(18)
    device = safe_get_device(device_sn, timeout=30, unmounted=True)
    config = GeneralConfig()
    if config.set_configs(device, quick_config=True):
        device.config.applyConfig()
        time.sleep(5)
        device.command.reset()