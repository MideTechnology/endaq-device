"""
Pytest configuration functions.
"""

import pytest


def pytest_addoption(parser):
    """
    Adds a command line option to list a device by serial number. These are 
    argparse style options.
    """

    parser.addoption(
        "-D", "--device", default=None, help="Specify the serial number of the device to test"
    )


def pytest_configure(config):
    """
    Registers the device type marks.
    """
    config.addinivalue_line(
        "markers", "device_w: mark test to run only when a W is connected"
    )
    config.addinivalue_line(
        "markers", "device_s: mark test to run only when an S is connected"
    )
    config.addinivalue_line(
        "markers", "device_needed: mark test to run only when a device is connected"
    )


def pytest_collection_modifyitems(config, items):
    """
    Defines how to treat tests with device type marks depending on the device 
    command line input.
    """
    if config.getoption("--device") is None:
        skip_test = pytest.mark.skip(
            reason="Run using local option, skipping device required tests")
        for item in items:
            if "device_needed" in item.keywords:
                item.add_marker(skip_test)
    elif config.getoption("--device")[0] == "S":
        skip_test = pytest.mark.skip(
            reason="Run using local option, skipping device required tests")
        for item in items:
            if "device_w" in item.keywords:
                item.add_marker(skip_test)
    elif config.getoption("--device")[0] == "W":
        skip_test = pytest.mark.skip(
            reason="Run using local option, skipping device required tests")
        for item in items:
            if "device_s" in item.keywords:
                item.add_marker(skip_test)


def pytest_generate_tests(metafunc):
    """
    This function will get called with any tests run from this directory. Print 
    does not work here. This is run before any of the other fixtures and tests, 
    and we use it to set some parameters that are only known at run time.
    """
    device_sn = metafunc.config.getoption("device")
    metafunc.parametrize("device_sn", [device_sn], scope="session")
