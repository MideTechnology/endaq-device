from copy import deepcopy
import logging
import os.path
import requests
import socket
from typing import Any, Callable, Dict, Optional, Union
from urllib.parse import urljoin
from endaq.device.command_interfaces import SerialCommandInterface
from endaq.device.devinfo import SerialDeviceInfo
from endaq.device.exceptions import CommandError
from endaq.device.gateway import Gateway
from endaq.device.mqtt.discovery import MDNSInfo, findBrokers
from endaq.device import CommunicationError
from endaq.device.util import encodeDict, decodeDict

from endaq.device.base import Recorder, NonRecorder

logger = logging.getLogger(__name__)

# XXX: TEST; TO BE UPDATED/REMOVED
CERTFILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'cert.pem')
# CERTFILE = False


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
        except requests.exceptions.ConnectionError as _err:

            # TODO: COMPLETE THIS (if necessary)
            raise


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

    :param info: The HTTPS device's advertised  info.
    :return: A base URL.
    """
    # Zeroconf default server names are just the service name and aren't
    # necessarily valid domain names. Use the IP if it can't be resolved.
    host = info.server
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror:
        host = info.host

    scheme = 'https' if info.properties.get(b'password', b'1') == b'1' else 'http'
    return f'{scheme}://{host}:{info.port}'


# ============================================================================
#
# ============================================================================

def getHttpsDevice(url: Union[str, MDNSInfo],
                   password: Optional[str] = None,
                   certfile: Optional[str] = None) -> "Recorder":
    """
    Create a recorder instance with an HTTPS interface.

    :param url: The device's base URL, or an `MDNSInfo` object as
        returned by `endaq.device.mqtt.discovery.findBrokers()`.
    :param password: The device's password, if any.
    :param certfile:
    """
    if isinstance(url, MDNSInfo):
        url = info2url(url)

    # Dummy recorder and command interface to retrieve DEVINFO
    fake = NonRecorder(name='getHttpsDevice')
    fake.command = HTTPSCommandInterface(fake, url, password, certfile)
    info = fake.command._getInfo(0, index=False, timeout=3)

    device = Gateway(None, devinfo=info)
    device.command = HTTPSCommandInterface(device, url, password, certfile)
    device._devinfo = SerialDeviceInfo(device)

    return device
