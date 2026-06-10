"""
Pytest configuration functions.
"""
import pytest
from typing import Tuple, List
from test_hardware.session_manager import SessionManager
import random
import re
import sys
from copy import copy 
from pathlib import Path

pytest_plugins = [
    'test_hardware.fixtures'
]


#===== HELPERS =====#
SESSION_MANAGER = None 

def _apply_wifi_toggles(items) -> List:
    """
    A helper for `pytest_collect_modifyitems`, used to 
    
    HACK: This function relies on string parsing, which is inheritely susceptible 
    to change. This function should be monitored for every significant pytest update.
    """
    pattern = re.compile(r".*\[.*(enable_wifi|disable_wifi).*]")
    for item in items:    
        matches = pattern.search(item.name)
        if matches:
            """
            The two lines of code below are temporarily disabled for the current PR.
            This is actively being developed in the wifi_device_tests branch
            
            item.fixturenames = copy(item.fixturenames)
            item.fixturenames.append(matches.group(1))
            """
            if matches.group(1) == "enable_wifi":
                item.add_marker(pytest.mark.wifi)
            else:
                item.add_marker(pytest.mark.no_wifi)
    return items

def _seperate_by_cond(items, cond) -> Tuple[List, List]:
    """
    :param cond: a function that takes in a singular item and returns a boolean 
    """
    cond_false = []
    cond_true = []
    for item in items: [cond_false, cond_true][cond(item)].append(item)
    return (cond_false, cond_true)
        
#==== Hooks =====#
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
    parser.addoption('--random-order', action="store_true", default=False, help=(
        "Include to randomize test execution order"
    ))
    parser.addoption("--random-order-seed", type=int, default=None, help=(
        "Included to give the randomizer a set seed."
    ))
    parser.addoption("-C", "--config", default="./endaq-device/mosquitto.conf", help= ("Specifies a "
    "mosquitto config file, for wifi tests (if applicable). Defaults to endaq-device/mosquitto.conf"
    ))

def pytest_configure(config):
    global SESSION_MANAGER
    SESSION_MANAGER = SessionManager(
        device_sn = config.getoption('--device'), 
        interface_mode = 2 if config.getoption('--raspi') else 1 if sys.stdin.isatty() else 0,
        get_on_init=True
        )

def pytest_generate_tests(metafunc):
    global SESSION_MANAGER
    has_wifi = SESSION_MANAGER.device.hasWifi
    #wifi only tests should get deselected, but still generated
    markers = metafunc.definition.own_markers
    marker_names = map(lambda mark: mark.name if hasattr(mark, "name") else False, markers)
    metafunc.fixturenames.append('wifi_toggle')
    
    parametrize_with = []
    
    if "no_wifi" in marker_names:
        parametrize_with.append('disable_wifi')
    elif "wifi" in marker_names:
        parametrize_with.append('enable_wifi')
        
    if parametrize_with == []:
        parametrize_with.append('disable_wifi')
        if has_wifi:
            parametrize_with.append('enable_wifi')

    metafunc.parametrize('wifi_toggle', parametrize_with)

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
    if config.getoption('--verbose'):
        print('duplicating and seperating tests')
    is_raspi: bool = config.getoption('--raspi')
    no_tty: bool = ((config.getoption('-s') != "no" or config.getoption('--no_tty'))
                    and not is_raspi)
    wifi_compatible: bool = SESSION_MANAGER.device.hasWifi

    selected = _apply_wifi_toggles(items)
    deselected = []

    conditions = []
    conditions.append(lambda item: not (no_tty and 'tty' in item.keywords)) #no_tty

    for cond in conditions:
        func_out = _seperate_by_cond(selected, cond)
        deselected += func_out[0]
        selected = func_out[1]
    #wifi
    wifi_out = _seperate_by_cond(selected, lambda item: ('wifi' in item.keywords))
    #random output
    if config.getoption('--random-order'):
        if config.getoption('--verbose'):
            print('randomizing tests')
        shuffler = random.Random(config.getoption('--random-order-seed')).shuffle
        shuffler(wifi_out[0])
        shuffler(wifi_out[1])
    selected = wifi_out[0]
    if wifi_compatible: 
        selected += wifi_out[1]
    else:
        deselected += wifi_out[1]
    config.hook.pytest_deselected(items = deselected)
    selected.sort(key = lambda item: 'wifi' in item.keywords)
    items[:] = selected

