"""
Pytest configuration functions.
"""
import pytest
from typing import Tuple, List, Set, Literal
from test_hardware.session_manager import SessionManager
import random
import re
import sys
from copy import copy 
from functools import cache

pytest_plugins = [
    'test_hardware.fixtures'
]

#===== GLOBAL VARIABLES ====#
#INVARIANT: all globals are modifed in pytest_configure, which
#by definition is the first thing ran

SESSION_MANAGER: SessionManager = None
INTERACTABLE: Literal["", "tty", "raspi"]= ""

#===== HELPERS =====#

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
                item.add_marker(pytest.mark.serial)
    return items

def _seperate_by_cond(items, cond) -> Tuple[List, List]:
    """
    :param cond: a function that takes in a singular item and returns a boolean 
    """
    cond_false = []
    cond_true = []
    for item in items: [cond_false, cond_true][cond(item)].append(item)
    return (cond_false, cond_true)

@cache
def _interactable(config) -> str:
   """
   Checks to see if a device can be interacted with, through a raspberry pi,
   or human input.
   Note that this method is cached using `functools.cache`, as the value should theoretically
   never change
   
   :param config: the config fixture found in `pytest_configure` or `pytest_collect_modifyitems`.
       Note that this is not a hook, and config has to be passed in manually

   :return: a boolean if there is some way to interact with this device
   """
   if config.getoption('--raspi'):
       return "raspi"
   if config.getoption('-no_tty'):
       return ""
   if config.getoption('-s') == "no":
       return "tty"
   return ""

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

def pytest_configure(config):
    """
    Used to set global variables, which allow other files to 
    use information that is only retrievable from `config`
    """
    global SESSION_MANAGER
    global INTERACTABLE
    SESSION_MANAGER = SessionManager(
        device_sn = config.getoption('--device'), 
        interface_mode = 2 if config.getoption('--raspi') else 1 if sys.stdin.isatty() else 0,
        get_on_init=True
        )
    INTERACTABLE = _interactable(config)


def pytest_generate_tests(metafunc):
    global SESSION_MANAGER
    global INTERACTABLE
    has_wifi = SESSION_MANAGER.device.hasWifi
    #wifi only tests should get deselected, but still generated
    markers = metafunc.definition.own_markers
    marker_names = map(lambda mark: mark.name if hasattr(mark, "name") else False, markers)
    metafunc.fixturenames.append('wifi_toggle')
    
    parametrize_with = []
    
    if "serial" in marker_names:
        parametrize_with.append('disable_wifi')
    elif "wifi" in marker_names:
        parametrize_with.append('enable_wifi')
        
    if parametrize_with == []:
        parametrize_with.append('disable_wifi')
        if has_wifi:
            parametrize_with.append('enable_wifi')
    #FUTURE: if, this logic needs to be updated
    if len(parametrize_with) == 2 : 
        print("unable to toggle between states with no method of interaction"
              "connect to a raspberry pi or use -s without --no_tty") 
        sys.exit(4) #exit code 4: command line error
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
    no_tty: bool = _interactable(config) 
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

