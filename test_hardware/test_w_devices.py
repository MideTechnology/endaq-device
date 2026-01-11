"""
Automated tests for W-specific commands in endaq.device
"""
import time
import warnings
import pytest
import os
import endaq.device
from endaq.device.response_codes import WiFiConnectionStatus, WiFiConnectionError
from test_hardware.helper_functions.raspi_endaq_controller import timed_button_press, set_button, set_usb
from test_hardware.helper_functions.general_config import GeneralConfig
from test_hardware.helper_functions.connection_helper import safe_get_device, wait_for_status, stopRecOldFW

# Helper Functions
def commandWait(device, timeout):
    """ Wait for the device to reconnect after a command is sent.

        :param device: Connected device.
        :param timeout: Time (seconds) to wait for the device to reconnect.
    """

    for _ in range(int(timeout)):
        try:
            resp = device.command.ping()
            print(f"Status code: {device.command.status=}\t"
                  "message: {dev.command.status[1]}")
            if device.command.status[1] == endaq.device.response_codes.DeviceStatusCode.RECORDING or \
                    device.command.status[1] == endaq.device.response_codes.DeviceStatusCode.IDLE_UNMOUNTED:
                print(
                    f"Device is recording. Status code: {device.command.status[1]}")

        except Exception as e:
            print(f"Got error {e}")

        # Getting here means that either expected_path is none and devices still
        # connected or the specific device path has not left yet
        time.sleep(1)


@pytest.fixture # with a default scope of "function"
def setupTeardown():
    """ Properly reset the enDAQ before and after every test.
    """
    # Setup
    # Reset the device and reconnect
    timed_button_press(18)
    device = safe_get_device(timeout=15)
    # Make sure the Wifi is turned on, clear any pre-recording delay, and set a 2 minute time limit
    config_dict = {"WifiEnable": 1, "PreRecordingDelay": 0, "RecordingTimeLimit": 120}
    config = GeneralConfig(**config_dict)
    if config.set_configs(device, quick_config=True):
        device.config.applyConfig()
        device.command.reset()      # Need to reset the device to turn the wifi on
        device = safe_get_device(timeout=15)

    device.command.ping()
    if (device.command.status[1] ==
        endaq.device.response_codes.DeviceStatusCode.RECORDING):
        device.command.stopRecording()

    yield # Runs test

    # Teardown
    print("Tearing down...")
    wait_for_status(device, [endaq.device.response_codes.DeviceStatusCode.IDLE], timeout=10)
    if (device.command.status[1] ==
        endaq.device.response_codes.DeviceStatusCode.RECORDING):
        device.command.stopRecording()

    print("Test complete")


# W Specific Tests
@pytest.mark.device_w
def test_get_network_address(device_sn, setupTeardown):
    """ Test that 'getNetworkAddress()' returns a valid MAC Address on W
        devices.

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the 
            enDAQ before and after every test.
    """
    # Set up
    device = endaq.device.getDevices()[0]

    # Gather the MAC and IP addresses
    mac, ip = device.command.getNetworkAddress()

    # Confirm that a valid MAC address was found
    assert mac != None, "MAC Address was None."
    print("MAC Address:", mac)

    time.sleep(5)


@pytest.mark.device_w
def test_get_network_status(device_sn, setupTeardown):
    """ Tests that 'getNetworkStatus()' returns the correct MAC and IP address 
        for cases where the device is connected or disconnected from wifi.

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the 
            enDAQ before and after every test.
    """
    # Set up
    device = endaq.device.getDevices()[0]
    guest_wifi_pw = os.environ.get("GUEST_WIFI_PW")

    # Connected Case
    device.command.setAP("MIDE-Guest", password=guest_wifi_pw )
    time.sleep(5)
    mac, ip = device.command.getNetworkAddress()
    network_status_connected = device.command.getNetworkStatus()

    mac_byte_array = network_status_connected["MACAddress"]
    mac_hex_string = ":".join("{:02X}".format(b) for b in mac_byte_array)
    assert mac_hex_string == mac, "MAC Address changed."

    ip_byte_array = network_status_connected["IPV4Address"]
    ip_address = ".".join(str(b) for b in ip_byte_array)
    assert ip_address == ip, "IP Address Changed."

    # Disconnected Case
    disconnected_ip = "0.0.0.0"
    device.command.setAP("Invalid-Wifi", password="InvalidPassword")
    time.sleep(5)
    network_status_disconnected = device.command.getNetworkStatus()

    mac_byte_array = network_status_disconnected["MACAddress"]
    mac_hex_string = ":".join("{:02X}".format(b) for b in mac_byte_array)
    assert mac_hex_string == mac, "MAC Address changed."

    ip_byte_array = network_status_disconnected["IPV4Address"]
    ip_address = ".".join(str(b) for b in ip_byte_array)
    assert ip_address == disconnected_ip, "IP Address Found."


@pytest.mark.device_w
def test_query_wifi(device_sn, setupTeardown):
    """ Tests that 'queryWifi()' returns the correct SSID and connection status
        for cases where the device is connected or disconnected from wifi.

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the 
            enDAQ before and after every test.
    """
    # Set up
    device = endaq.device.getDevices()[0]
    guest_wifi_pw = os.environ.get("GUEST_WIFI_PW")

    # Connected Case
    device.command.setAP("MIDE-Guest", password=guest_wifi_pw)
    time.sleep(10)
    connected_query = device.command.queryWifi()
    assert connected_query["SSID"] == "MIDE-Guest", "Connected to wrong wifi."
    assert (connected_query["WiFiConnectionStatus"] ==
            WiFiConnectionStatus.CONNECTED), "Not Connected."

    # Disconnected Case
    device.command.setAP("Invalid-Wifi", password="InvalidPassword")
    time.sleep(10)
    disconnected_query = device.command.queryWifi()
    assert disconnected_query["SSID"] == "", "Connected to a wifi."
    assert (disconnected_query["WiFiConnectionStatus"] !=
            WiFiConnectionStatus.CONNECTED), "Connected to invalid wifi."
    assert (disconnected_query["WiFiConnectionStatus"] ==
            WiFiConnectionStatus.IDLE), "Wifi not idle"
    assert (disconnected_query["WiFiConnectionError"] ==
            WiFiConnectionError.ERR_NO_AP_FOUND), "Expected error not present"


@pytest.mark.device_w
def test_scan_wifi(device_sn, setupTeardown):
    """ Tests that 'scanWifi()' can find three MIDE wifi networks. Warns if the
        connection strength for any of the three are weak.

        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the 
            enDAQ before and after every test.
    """
    # Set up
    LIST_OF_NETWORKS = ["MIDE-Corp", "Mide-LinuxNet", "MIDE-Guest"]
    STRENGTH_CUTOFF = -80
    device = endaq.device.getDevices()[0]
    network_indices = []

    # Find connected networks
    found_networks = device.command.scanWifi()
    assert found_networks != [], "No networks found."

    # Check for connection to 3 expected networks
    for index, dictionary in enumerate(found_networks):
        if dictionary.get("SSID") in LIST_OF_NETWORKS:
            network_indices.append(index)
    assert len(network_indices) >= 3, "Did not identify all expected networks."
    assert len(network_indices) < 4, "Identified unexpected duplicate networks."

    # Check the strength of these network connections
    for index in network_indices:
        network_dict = found_networks[index]
        if network_dict["RSSI"] <= STRENGTH_CUTOFF:
            warnings.warn(f"Weak connection to {network_dict["SSID"]}", Warning)


@pytest.mark.device_w
@pytest.mark.parametrize("SSID", ["MIDE-Guest", "Invalid-Wifi"])
def test_set_AP(SSID, device_sn, setupTeardown):
    """ Tests that 'setAP()' will establish a connection when given a valid SSID
        and password and will not if the SSID or password are invalid.

        :param SSID: a parameterized name of a wifi network.
        :param device_sn: the tested device's serial number collected from the 
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the 
            enDAQ before and after every test.
    """
    # Set up
    device = endaq.device.getDevices()[0]
    guest_wifi_pw = os.environ.get("GUEST_WIFI_PW")

    # Attempt to run setAP
    match SSID:
        case "MIDE-Guest":
            # Valid PW case
            device.command.setAP(SSID, password=guest_wifi_pw)
            query_wifi = device.command.queryWifi()
            time.sleep(10)
            assert (query_wifi["WiFiConnectionStatus"] ==
                    WiFiConnectionStatus.CONNECTED
                    ), "Didn't connect to MIDE-Guest with valid PW."

            # Invalid PW case
            device.command.setAP(SSID, password="InvalidPassword")
            query_wifi = device.command.queryWifi()
            time.sleep(10)
            assert (query_wifi["WiFiConnectionStatus"] !=
                    WiFiConnectionStatus.CONNECTED
                    ), "Connected to Mide_Guest with invalid PW."

        case "Invalid-Wifi":
            # Invalid Wifi and PW case
            device.command.setAP(SSID, password="InvalidPassword")
            query_wifi = device.command.queryWifi()
            time.sleep(10)
            assert (query_wifi["WiFiConnectionStatus"] !=
                    WiFiConnectionStatus.CONNECTED
                    ), "Connected to Invalid Wifi."


@pytest.mark.skip
def test_set_wifi(device_sn, setupTeardown):
    """
    Can probably be SKIPPED since 'setAP()' calls 'setWifi()'
    """
    pass


@pytest.mark.skip
def test_update_ESP32(device_sn, setupTeardown):
    """
    DON'T TEST

    We should not test this right now, modern devices have an all-in-one update 
    so the main processor and ESP32 are updated together.
    """
    pass
