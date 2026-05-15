"""
Automated tests for W-specific commands in endaq.device
"""
import time
import pytest
import sys
import os
import warnings
import endaq.device
from endaq.device.response_codes import WiFiConnectionStatus, WiFiConnectionError

# W Specific Tests
@pytest.mark.wifi
def test_get_network_address(device_manager):
    """ Test that 'getNetworkAddress()' returns a valid MAC Address on W
        devices.

        :param device_sn: the tested device's serial number collected from the
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    device = device_manager.device

    # Gather the MAC and IP addresses
    mac_addr, _ = device.command.getNetworkAddress()

    # Confirm that a valid MAC address was found
    assert mac_addr != None, "MAC Address was None."
    print("MAC Address:", mac_addr)


@pytest.mark.wifi
def test_get_connected_network_status(device_manager):
    """ Tests that 'getNetworkStatus()' returns the correct MAC and IP address
        for cases where the device is connected or disconnected from wifi.

        :param device_sn: the tested device's serial number collected from the
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    device = device_manager.device
    guest_wifi_pw = os.environ.get("GUEST_WIFI_PW", "nopwd")

    # Connected Case
    device.command.setAP("MIDE-Guest", password=guest_wifi_pw)
    device.command.awaitReconnect()
    mac_addr, ip = device.command.getNetworkAddress()
    assert mac_addr is not None, "No MAC address retreived"
    assert ip is not None, "No IP address retreived, could be wifi connection issue"

    network_status_connected = device.command.getNetworkStatus()

    assert network_status_connected is not None, "Failed to get network status"

    mac_byte_array = network_status_connected["MACAddress"]
    mac_hex_string = ":".join("{:02X}".format(b) for b in mac_byte_array)
    assert mac_hex_string == mac_addr, "MAC Address changed between getNetworkAddress and getNetworkStatus."

    ip_byte_array = network_status_connected["IPV4Address"]
    ip_address = ".".join(str(b) for b in ip_byte_array)
    assert ip_address == ip, "IP Address Changed."

    # Disconnected Case
    disconnected_ip = "0.0.0.0"
    device.command.setAP("Invalid-Wifi", password="InvalidPassword")
    device.command.awaitReconnect()
    network_status_disconnected = device.command.getNetworkStatus()

    assert network_status_connected is not None, "Failed to get network status"

    mac_byte_array = network_status_disconnected["MACAddress"]
    mac_hex_string = ":".join("{:02X}".format(b) for b in mac_byte_array)
    assert mac_hex_string == mac_addr, "MAC Address changed."

    ip_byte_array = network_status_disconnected["IPV4Address"]
    ip_address = ".".join(str(b) for b in ip_byte_array)
    assert ip_address == disconnected_ip, "IP Address Found."


@pytest.mark.wifi
def test_query_wifi(device_manager):
    """ Tests that 'queryWifi()' returns the correct SSID and connection status
        for cases where the device is connected or disconnected from wifi.

        :param device_sn: the tested device's serial number collected from the
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    device = device_manager.device
    guest_wifi_pw = os.environ.get("GUEST_WIFI_PW", "nopwd")

    # Connected Case
    device.command.setAP("MIDE-Guest", password=guest_wifi_pw)
    device.command.awaitReconnect()
    connected_query = device.command.queryWifi()
    assert connected_query is not None, "Got no reply to queryWifi with correct setAP"
    assert (connected_query["WiFiConnectionStatus"] ==
            WiFiConnectionStatus.CONNECTED), "Did not connect to wifi."
    assert connected_query["SSID"] == "MIDE-Guest", "Connected to wrong wifi."

    # Disconnected Case
    device.command.setAP("Invalid-Wifi", password="InvalidPassword")
    device.command.awaitReconnect()
    disconnected_query = device.command.queryWifi()
    assert disconnected_query is not None, "Got no reply to queryWifi with bad setAP"
    assert disconnected_query["SSID"] == "", "Connected to a wifi when we sent bad info"
    assert (disconnected_query["WiFiConnectionStatus"] !=
            WiFiConnectionStatus.CONNECTED), "Connected to invalid wifi."
    assert (disconnected_query["WiFiConnectionStatus"] ==
            WiFiConnectionStatus.IDLE), "Wifi not idle"
    assert (disconnected_query["WiFiConnectionError"] ==
            WiFiConnectionError.ERR_NO_AP_FOUND), "Expected error not present"

@pytest.mark.wifi
def test_scan_wifi(device_manager):
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
    device = device_manager.device
    network_indices = []

    # Find connected networks
    found_networks = device.command.scanWifi()
    assert found_networks != [], "No networks found."

    # Check for connection to 3 expected networks
    for index, dictionary in enumerate(found_networks):
        if dictionary.get("SSID", "") in LIST_OF_NETWORKS:
            network_indices.append(index)
    assert len(network_indices) >= 3, "Did not identify all expected networks."
    assert len(network_indices) < 4, "Identified unexpected duplicate networks."

    # Check the strength of these network connections
    for index in network_indices:
        network_dict = found_networks[index]
        if network_dict["RSSI"] <= STRENGTH_CUTOFF:
            warnings.warn(f"Weak connection to {network_dict["SSID"]}", Warning)


@pytest.mark.wifi
def test_set_AP(device_manager):
    """ Tests that 'setAP()' will establish a connection when given a valid SSID
        and password and will not if the SSID or password are invalid.

        :param SSID: a parameterized name of a wifi network.
        :param device_sn: the tested device's serial number collected from the
            command line.
        :param setupTeardown: a pytest fixture function that properly resets the
            enDAQ before and after every test.
    """
    # Set up
    device = device_manager.device
    guest_wifi_pw = os.environ.get("GUEST_WIFI_PW", "nopwd")

    # Valid PW case
    device.command.setAP("MIDE-Guest", password=guest_wifi_pw)
    device.command.awaitReconnect()
    query_wifi = device.command.queryWifi()
    assert query_wifi is not None, "Got no reply to queryWifi when connecting to MIDE-Guest"
    assert (query_wifi["WiFiConnectionStatus"] ==
            WiFiConnectionStatus.CONNECTED
            ), "Didn't connect to MIDE-Guest with valid PW."

@pytest.mark.wifi
def test_set_invalid_AP(device_manager):
    device = device_manager.device
    device.command.setAP("invalid", password="invalid")
    device.command.awaitReconnect() #TODO: correct?
    query_wifi = device.command.queryWifi()
    assert query_wifi is not None, "queryWifi didn't respond to invalid WiFi"
    assert query_wifi['WiFiConnectionStatus'] != WiFiConnectionStatus.CONNECTED, "Connected to invalid wifi"
    
@pytest.mark.skip
@pytest.mark.wifi
def test_set_wifi(device_manager):
    """
    Can probably be SKIPPED since 'setAP()' calls 'setWifi()'
    """
    pass


@pytest.mark.skip
@pytest.mark.wifi
def test_update_ESP32(device_manager):
    """
    DON'T TEST

    We should not test this right now, modern devices have an all-in-one update
    so the main processor and ESP32 are updated together.
    """
    pass
