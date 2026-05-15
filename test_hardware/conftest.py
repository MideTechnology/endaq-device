"""
Pytest configuration functions.
"""

import pytest
import endaq.device

pytest_plugins = [
    'test_hardware.fixtures'
]

def pytest_addoption(parser):
    """
    Adds a command line option to list a device by serial number. These are 
    argparse style options.
    """

    parser.addoption(
        "-D", "--device", required=True, default=None, help="Specify the serial number of the device to test"
    )
    parser.addoption(
        "-R", "--raspi", action="store_true", default=False, help="Include if running on a RasPi"
    )
    parser.addoption('--no_tty', action="store_true", default=False, help="")
    parser.addoption(
        "-N", "--num_attempts", type=int, default = 3, help="Sets the number of times to retry a test "\
            "in case of a unexpected error."
    )

def pytest_exception_interact(node, call, report):
    """
    This is used to cleanup any tests that resulted in a failure.
    `device_manager` is passed in automatically to every single test, so if the test runs,
    it is guarenteed to be accessible.
    NOTE: If the test crashes on a fixture (eg: not having a device plugged in), 
        then there will be no funcargs / device_manager key.
    """
    if hasattr(node, 'funcargs') and 'device_manager' in node.funcargs:
        node.funcargs['device_manager'].end_test(True)


def pytest_collection_modifyitems(config, items):
    """
    Defines how to treat tests with device type marks depending on the device 
    command line input.
    """
    device = config.getoption("--device")
    
    if device[0].upper() == "S":
        skip_test = pytest.mark.skip(
            reason="Test not required for S device")
        for item in items:
            if "device_w" in item.keywords:
                item.add_marker(skip_test)
    elif device[0].upper() == "W":
        skip_test = pytest.mark.skip(
            reason="Test not required for W device")
        for item in items:
            if "device_s" in item.keywords:
                item.add_marker(skip_test)
    else:
        raise ValueError(f"Input parameter {device} not recognized. Expected format is an enDAQ serial number, starting with W or S")
    for item in items:
        if 'tty' in item.keywords and (
            (config.getoption('-s') != "no" or config.getoption('--no_tty')) and not config.getoption('--raspi')
            ):
            item.add_marker(pytest.mark.skip("test requires user / raspi input"))


@pytest.fixture(autouse=True)
def can_wifi(device_manager, request):
    """
    psuedo-collection_modifyitems used to skip WiFi tests for non-WiFi devices, 
    which can only be done with a device_manager.
    """
    if request.node.get_closest_marker('wifi') and not device_manager.device.hasWifi:
        pytest.skip("test requires WiFi compatible device")