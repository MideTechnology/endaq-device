"""
Contains fixtures used in device tests. Note that some fixtures are in `conftest.py`
"""
from test_hardware.device_manager import DeviceManager, safe_get_device
import pytest
from functools import wraps
import sys
from test_hardware.helper_functions.hardware_interface import *
from test_hardware.helper_functions.general_config import GeneralConfig

#===   ===#
@pytest.fixture(scope="session")
def is_raspi(request) -> bool:
    return request.config.getoption("--raspi")

@pytest.fixture(scope="session")
def device_sn(request) -> bool:
    return request.config.getoption("--device")

@pytest.fixture(autouse=True)
def test_cleanup(device_manager):
    yield
    device_manager.end_test(False)

@pytest.fixture(scope="session", autouse=True)
def device_manager(device_sn, is_raspi):
    yield DeviceManager(
        device_sn = device_sn, 
        interface_mode = 2 if is_raspi else 1 if sys.stdin.isatty() else 0,
        get_on_init=True
        )


@pytest.fixture(scope="session", autouse=True)
def setupTeardownSession(device_manager):
    """ Set up and teardown GPIO RasPi controls at the beginning and end
        of a session.

        :param is_raspi: True if the tests are meant to run on a RaspberryPi,
            False otherwise. Set in command line.
    """
    # Put the device in default configuration
    has_wifi = device_manager.device.hasWifi
    print(f"Setting up session")
    config_dict = {
        "WifiEnable": 1 if has_wifi else 0, 
        "PreRecordingDelay": 0, 
        "RecordingTimeLimit": 120
        }
    hw = device_manager.hw_interface
    config = GeneralConfig(**config_dict)
    if config.set_configs(device, quick_config=True):
        print(f"Applying updated config")
        device.config.applyConfig()
        device.command.reset()  # Need to reset the device to turn the wifi on
        device = safe_get_device(timeout=30) # Wait for device to come back

    # Always update the device configuration
    if isinstance(device_manager.hw_interface, RaspiInterface):
        print("\nSetting up RasPi...")
        hw.set_usb(True)
        hw.set_button(False)

        yield

        print("\nTearing down RasPi setup...")
        hw.set_usb(True)
        hw.set_button(False)

        print("\nDone with RasPi tear down.")
    else:
        yield
    device_manager.end_session()
    print(f"Finished session")

