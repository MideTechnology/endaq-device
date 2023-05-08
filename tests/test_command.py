"""
Tests of the command interfaces.
"""

from copy import deepcopy
import os.path
import pytest

import endaq.device
from endaq.device import getRecorder
from endaq.device.command_interfaces import CommandInterface, FileCommandInterface

from .fake_recorders import RECORDER_PATHS
from .mock_hardware import applyMockCommandIO

# Clear any cached devices, just to be safe
endaq.device.RECORDERS.clear()

# Create parameters, mainly to provide an ID, making the results readable
DEVICES = [pytest.param(getRecorder(path, strict=False), id=os.path.basename(path)) for path in RECORDER_PATHS]
SERIAL_DEVICES = [param for param in DEVICES if not isinstance(param[0][0].command, FileCommandInterface)]
WIFI_DEVICES = [param for param in DEVICES if param[0][0].hasWifi]

# Response to a `scanWifi()` command
WIFI_SCAN = {'EBMLResponse': {'CMDQueueDepth': 1,
                  'DeviceStatusCode': 0,
                  'ResponseIdx': 1,
                  'WiFiScanResult': {'AP': [{'AuthType': 3,
                                             'Known': True,
                                             'RSSI': -58,
                                             'SSID': 'MIDE-Guest',
                                             'Selected': True},
                                            {'AuthType': 3,
                                             'Known': False,
                                             'RSSI': -58,
                                             'SSID': 'Example AP 1',
                                             'Selected': False},
                                            {'AuthType': 3,
                                             'Known': False,
                                             'RSSI': -81,
                                             'SSID': 'Example AP 2',
                                             'Selected': False},
                                            {'AuthType': 3,
                                             'Known': False,
                                             'RSSI': -83,
                                             'SSID': 'Example AP 3',
                                             'Selected': False},
                                            {'AuthType': 3,
                                             'Known': False,
                                             'RSSI': -90,
                                             'SSID': 'Example AP 4',
                                             'Selected': False},
                                            {'AuthType': 3,
                                             'Known': False,
                                             'RSSI': -94,
                                             'SSID': 'Example AP 5',
                                             'Selected': False}],
                                     'ScanVersion': 3}}}


@pytest.mark.parametrize("dev", DEVICES)
def test_command_basics(dev):
    """ Initial 'sanity test' to verify `CommandInterface` instances are
        being instantiated.
    """
    assert isinstance(dev.command, CommandInterface)


@pytest.mark.parametrize("dev", SERIAL_DEVICES)
def test_command_ping(dev):
    """ Test the `ping()` command on devices that support it.
    """
    mock_io = applyMockCommandIO(dev)
    mock_io.response = mock_io.encodeResponse({'EBMLResponse':
                                               {'ResponseIdx': dev.command.index + 1,
                                                'CMDQueueDepth': 1,
                                                'DeviceStatusCode': 0,
                                                'PingReply': bytearray(b'hello')}},
                                              resultcode=0)
    
    assert dev.command.ping() == bytearray(b'hello')


@pytest.mark.parametrize("dev", WIFI_DEVICES)
def test_command_scanWifi(dev):
    """ Test the `scanWifi()` command on devices that support it.
    """
    mock_io = applyMockCommandIO(dev)
    response = deepcopy(WIFI_SCAN)
    response['EBMLResponse']['ResponseIdx'] = dev.command.index + 1
    mock_io.response = mock_io.encodeResponse(response)
    assert dev.command.scanWifi() == response['EBMLResponse']['WiFiScanResult']['AP']