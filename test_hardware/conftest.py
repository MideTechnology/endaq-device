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
    `session_manager` is passed in automatically to every single test, so if the test runs,
    it is guarenteed to be accessible.
    NOTE: If the test crashes on a fixture (eg: not having a device plugged in), 
        then there will be no funcargs / session_manager key.
    """
    if hasattr(node, 'funcargs') and 'session_manager' in node.funcargs:
        node.funcargs['session_manager'].end_test(True)

def pytest_collection_modifyitems(config, items):
    """
    Defines how to treat tests with device type marks depending on the device 
    command line input.
    """
    device = config.getoption("--device")
    for item in items:    
        #skipping tty tests if no tty
        if 'tty' in item.keywords and (
            (config.getoption('-s') != "no" or config.getoption('--no_tty')) and not config.getoption('--raspi')
            ):
            item.add_marker(pytest.mark.skip("test requires user / raspi input"))


@pytest.fixture(autouse=True)
def can_wifi(session_manager, request):
    """
    psuedo-collection_modifyitems used to skip WiFi tests for non-WiFi devices, 
    which can only be done with a session_manager.
    """
    if request.node.get_closest_marker('wifi') and not session_manager.device.hasWifi:
        pytest.skip("test requires WiFi compatible device")