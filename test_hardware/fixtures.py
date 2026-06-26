import pytest
import sys
from test_hardware.helper_functions.hardware_interface import *

#===   ===#
@pytest.fixture(scope="session")
def is_raspi(request) -> bool:
    return request.config.getoption("--raspi")

@pytest.fixture(scope="session")
def device_sn(request) -> bool:
    return request.config.getoption("--device")

@pytest.fixture(autouse=True)
def test_cleanup(session_manager):
    yield
    session_manager.end_test(False)

@pytest.fixture(scope="session", autouse=True)
def session_manager(device_sn, is_raspi):
    from test_hardware.conftest import SESSION_MANAGER
    yield SESSION_MANAGER

@pytest.fixture(scope="session", autouse=True)
def setupTeardownSession(session_manager):
    """ Set up and teardown GPIO RasPi controls at the beginning and end
        of a session.

        :param is_raspi: True if the tests are meant to run on a RaspberryPi,
            False otherwise. Set in command line.
    """
    print(f"Setting up session")
    hw = session_manager.hw_interface
    # Always update the device configuration
    if isinstance(session_manager.hw_interface, RaspiInterface):
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
    try:
        session_manager.end_session()
    except:
        pass #TODO:fix
    print(f"Finished session")

@pytest.fixture
def disable_wifi(session_manager):
    session_manager.toggle_connection("serial")
    yield

@pytest.fixture
def enable_wifi(session_manager):
    session_manager.toggle_connection("wifi")
    yield
