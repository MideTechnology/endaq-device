from copy import deepcopy
from fnmatch import fnmatchcase
import logging
import os.path
import requests
from requests.exceptions import ConnectTimeout
import socket
from threading import Thread
from time import sleep, time
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urljoin

import endaq.device
from endaq.device.command_interfaces import SerialCommandInterface
from endaq.device.devinfo import SerialDeviceInfo
from endaq.device.exceptions import CommandError
from endaq.device.gateway import Gateway
from endaq.device.mqtt.discovery import MDNSInfo, MDNSFinder, findBrokers
from endaq.device import CommunicationError
from endaq.device.util import encodeDict, decodeDict

from endaq.device.base import Recorder, NonRecorder

logger = logging.getLogger(__name__)

# XXX: TEST; TO BE UPDATED/REMOVED
# CERTFILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'cert.pem')
CERTFILE = False

__all__ = ('HTTPSCommandInterface', 'getDevices')


# ===========================================================================
#
# ===========================================================================

class HTTPSCommandInterface(SerialCommandInterface):
    """
    A mechanism for sending commands to a recorder via HTTP(S).
    """

    def __init__(self,
                 device: "Recorder",
                 url: str = 'http://localhost:8088/',
                 password: Optional[str] = None,
                 certfile: str = CERTFILE):
        """
        A mechanism for sending commands to a recorder via HTTP(S).

        :param device: The HTTP/HTTPS device.
        :param url: The device's base URL.
        :param password: The device's password, if any.
        """
        self.baseUrl = url
        self.url = urljoin(url, 'command')
        self.password = password
        self.certfile = certfile
        self._http_response: requests.Response = None
        super().__init__(device)


    @classmethod
    def hasInterface(cls, device: "Recorder") -> bool:
        """
        Determine if a device supports this `CommandInterface` type.

        :param device: The recorder to check.
        :return: `True` if the device supports the interface.
        """
        if device.isVirtual:
            return False

        return device.path and str(device.path).startswith('http')


    # noinspection method-overriding
    def getSerialPort(self,
                      reset: bool = False,
                      timeout: Union[int, float] = 1,
                      kwargs: Optional[Dict[str, Any]] = None) -> None:
        """
        This has no function in `HTTPSCommandInterface`, and only exists for
        compatibility with `SerialCommandInterface`.
        """
        return None


    # noinspection method-overriding
    def _encode(self,
                data: Dict[str, Any],
                checkSize: bool = True) -> Dict[str, Any]:
        """
        Prepare a packet of command data for transmission, doing any
        preparation required by the interface's medium.

        :param data: The unencoded command `dict`.
        :param checkSize: If `False`, skip the check that the length of the
            encoded command is not greater than the device's maximum.
            Not used by `HTTPSCommandInterface`.
        :return: The encoded command data, with any class-specific
            wrapping or other preparations.
        """
        copy = deepcopy(data)
        encodeDict(copy)
        return copy


    # noinspection method-overriding
    def _encodeResponse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encode a packet of response data in the manner typically received
        from devices, doing any preparation required by the interface's
        medium. Only used in some special cases; not generally used in
        ordinary "Recorder" communication.

        :param data: The unencoded command `dict`.
        :return: The encoded command data, with any class-specific
            wrapping or other preparations.
        """
        return self._encode(data)


    # noinspection method-overriding
    def _decode(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translate a response packet (a dictionary with encoded binary
        values, from JSON) into a decoded dictionary.

        :param packet: A packet of response data, decoded from JSON.
        :return: The response, as nested dictionaries.
        """
        try:
            copy = deepcopy(packet)
            decodeDict(copy)
            return copy

        except IOError as err:
            raise CommunicationError('Response from device could not be decoded '
                                     f'({err})')


    # noinspection method-overriding
    def _writeCommand(self,
                      packet: Dict[str, Any],
                      timeout: Union[int, float] = 30) -> int:
        """ Transmit a fully formed packet (addressed, HDLC encoded, etc.)
            via serial. This is a low-level write to the medium and does not
            do the additional housekeeping that `sendCommand()` does;
            typically, it should not be used directly.

            :param packet: The encoded, packetized, `EBMLCommand`
                data.
        """
        try:
            if self.password is not None:
                headers = {'X-Password': self.password}
            else:
                headers = None
            self._http_response = requests.post(
                    self.url,
                    json=packet,
                    headers=headers,
                    timeout=timeout,
                    verify=self.certfile
            )
            if not self._http_response.ok:
                raise CommandError(
                        self._http_response.status_code,
                        f'{self._http_response.reason}: {self._http_response.text}')
            return 1
        except requests.exceptions.ConnectionError as err:
            logger.error(f'Error making HTTPS request: {err}')
            raise CommunicationError(f'Error making HTTPS request: {err}')


    def _readResponse(self,
                      timeout: Optional[float] = 0.5,
                      callback: Optional[Callable] = None) -> Union[None, dict]:
        """
        Wait for and retrieve the response to a serial command. Does not do
        any processing other than (attempting to) decode the EBML payload.

        :param timeout: Time to wait for a valid response. `None` or -1 will
            wait indefinitely.
        :param callback: A function to call each response-checking
            cycle. If the callback returns `True`, the wait for a
            response will be cancelled. The callback function should
            require no arguments. Not used by `HTTPSCommandInterface`.
        :return: A `dict` of response data, or `None` if `callback` caused
            the process to cancel.
        """
        response = self._http_response.json()
        decodeDict(response)
        return response['EBMLResponse']


# ============================================================================
#
# ============================================================================

def info2url(info: MDNSInfo) -> str:
    """
    Generate a device's base URL from its mDNS advertised info.

    :param info: The HTTPS device's advertised  info. If `info` is a string,
        the string gets returned verbatim.
    :return: A base URL.
    """
    if isinstance(info, str):
        return info

    # Zeroconf default server names are just the service name and aren't
    # necessarily valid domain names. Use the IP if it can't be resolved.
    host = info.server.rstrip('.')
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror:
        logger.warning('Advertised server name invalid, using IP')
        host = info.host[0]

    scheme = str(info.properties.get(b'protocol', b'mqtt'), 'utf8').lower()
    if not scheme.startswith('http'):
        raise CommunicationError(f'Unsupported protocol: {scheme!r}')
    return f'{scheme}://{host}:{info.port}'


# ============================================================================
#
# ============================================================================

def getHttpsDevice(info: Union[str, MDNSInfo],
                   password: Optional[str] = None,
                   certfile: Optional[str] = None) -> "Recorder":
    """
    Create a recorder instance with an HTTPS interface.

    :param info: The device's base URL, or an `MDNSInfo` object as
        returned by `endaq.device.mqtt.discovery.findBrokers()`.
        Using `MDNSInfo` is more efficient.
    :param password: The device's password, if any.
    :param certfile:
    """
    if isinstance(info, MDNSInfo):
        url = info2url(info)
        devinfo = info.properties.get(b'devinfo', None)
    elif isinstance(info, str):
        url = info
        devinfo = None
    else:
        raise TypeError(f'Expected MDNSInfo or str, got {type(info)}')

    if 'https' not in url.lower():
        certfile = None

    if devinfo is None:
        # Dummy recorder and command interface to retrieve DEVINFO
        fake = NonRecorder(name='getHttpsDevice')
        fake.command = HTTPSCommandInterface(fake, url, password, certfile)
        devinfo = fake.command._getInfo(0, index=False, timeout=3)

    with endaq.device._module_busy:
        infohash = hash(devinfo)
        device = endaq.device.RECORDERS.pop(infohash, None)
        if device is None:
            device = Gateway(None, devinfo=devinfo)
            device.command = HTTPSCommandInterface(device, url, password, certfile)
            device._devinfo = SerialDeviceInfo(device)
        endaq.device.RECORDERS[infohash] = device
        endaq.device.RECORDERS_BY_SN[device.serialInt] = device

    return device


# ============================================================================
#
# ============================================================================

class DeviceGetterThread(Thread):
    """
    Thread for attempting to asynchronously instantiate an HTTP(S) device
    instance. Used by `endaq.device.https_interface.getDevices()`.
    """

    def __init__(self,
                 info: MDNSInfo,
                 certfile: Optional[str] = None):
        """

        :param info:
        :param certfile:
        """
        self.info = info
        self.certfile = certfile
        self.device = None
        self.exception = None

        super().__init__(daemon=True)
        self.name = self.name.replace('Thread', type(self).__name__)

        self.start()


    def run(self):
        """ Main thread loop.
        """
        try:
            self.device = getHttpsDevice(self.info,
                                         certfile=self.certfile)
        except ConnectTimeout as err:
            self.exception = err
            logger.error(f'Timed out connecting to {info2url(self.info)!r}, skipping')
        except Exception as err:
            self.exception = err
            logger.exception(f'Error getting device from {info2url(self.info)}')


# ============================================================================
#
# ============================================================================

def getDevices(scantime: Union[float, int] = 2,
               timeout: Union[float, int] = 20,
               callback: Optional[Callable] = None,
               keepalive: Union[float, int] = 180.0,
               certfile: Optional[str] = None,
               finder: Optional[MDNSFinder] = None) -> List[Recorder]:
    """
    Find enDAQ-advertised HTTP/HTTPS devices.

    :param scantime: The *minimum* time (in seconds) to scan for advertised
        HTTP/HTTPS devices. If any are discovered in this time, they will
        be returned.
    :param timeout: The *maximum* time (in seconds) to scan for devices, if
        none were found in `scantime`.
    :param callback: A function to call repeatedly while scanning. If the
        callback returns `True`, the wait for a response will be cancelled.
        The callback function should require no arguments.
    :param keepalive: If `True`, keep the mDNS finding object open for
        later use (this can make subsequent discovery faster and more
        accurate).
    :param certfile:
    :param finder: An existing, running `MDNSFinder` instance. Supplying
        one can make things faster.
    :returns: A list of MQTT Brokers.
    """
    devices = []

    if finder is not None:
        mdns = [broker for broker in finder.getBrokerList()
                if fnmatchcase(broker.properties.get(b'protocol', b'mqtt'), b'http*')]
    else:
        mdns = findBrokers(protocol='http*',
                           scantime=scantime,
                           timeout=timeout,
                           callback=callback,
                           keepalive=keepalive)

    if not mdns:
        return devices

    threads = [DeviceGetterThread(url, certfile=certfile) for url in mdns]

    deadline = time() + timeout
    while time() < deadline:
        if not any(thread.is_alive() for thread in threads):
            break
        sleep(0.1)
    for thread in threads:
        if thread.device:
            devices.append(thread.device)

    return devices
