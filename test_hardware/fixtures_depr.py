"""
holds depricated fixtures, should never need to be used, but kept as a good practice
NOTE: these will not be found by pytest. If wanted to be used, add `'test_hardware.fixtures_depr'`
to the `pytest_plugins` variable.
"""
import pytest
import sys
import time
from test_hardware.helper_functions.general_config import GeneralConfig
from test_hardware.device_manager import safe_get_device
from test_hardware.helper_functions.hardware_interface import MockInterface, TTYInterface, RaspiInterface

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