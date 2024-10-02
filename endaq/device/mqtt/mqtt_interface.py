"""
This module handles creating a connection to an MQTT broker, and
communicating with an MQTT Device Manager.

The main component in this module is `MQTTConnectionManager`.
"""

import logging
import socket
from threading import Event, Thread, get_native_id
from time import sleep, time
from typing import Any, Callable, Dict, List, Optional, Union
from weakref import WeakValueDictionary

import paho.mqtt.client as mqtt
from serial import PortNotOpenError

from ..client import synchronized
from ..command_interfaces import SerialCommandInterface
from ..devinfo import MQTTDeviceInfo
from ..exceptions import CommunicationError, DeviceError
from ..simserial import SimSerialPort

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..base import Recorder

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# ===========================================================================
#
# ===========================================================================

MQTT_BROKER = None  # "localhost"
MQTT_PORT = 1883
KEEP_ALIVE_INTERVAL = 60*60  #: MQTT client 'keep alive' time (seconds)
THREAD_KEEP_ALIVE_INTERVAL = 60 * 5  #: Thread 'keep alive' time (seconds) if there are no connections

# Default keyword arguments for `paho.mqtt.client.Client.__init__()` and `.connect()`
CLIENT_INIT_ARGS = (('callback_api_version', mqtt.CallbackAPIVersion.VERSION2),)
CLIENT_CONNECT_ARGS = ()

COMMAND_TOPIC = "endaq/{sn}/control/command"
RESPONSE_TOPIC = "endaq/{sn}/control/response"
STATE_TOPIC = "endaq/{sn}/control/state"
HEADER_TOPIC = "endaq/{sn}/header"
MEASUREMENT_TOPIC = "endaq/{sn}/measurement"



# ===========================================================================
#
# ===========================================================================

def getMyIP() -> str:
    """ Retrieve the computer's IP address (v4).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    addr = s.getsockname()[0]
    s.close()
    return addr


def makeClientID(base: str) -> str:
    """ Generate a unique but readable ID for the MQTT Client. The ID
        combines the name of a parent object, the machine's IP, and the
        thread ID from which the function was called.
    """
    # This is *probably* unique enough.
    return f'{base}_{getMyIP()}_{get_native_id()}'


# ===========================================================================
#
# ===========================================================================

class MQTTConnectionManager:
    """
    Class that manages the connection to the MQTT Broker and communication
    with the MQTT Device Manager.
    """

    def __init__(self,
                 host: str = MQTT_BROKER,
                 port: int = MQTT_PORT,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 mqttKeepAlive: int = KEEP_ALIVE_INTERVAL,
                 threadKeepAlive: int = THREAD_KEEP_ALIVE_INTERVAL,
                 clientArgs: Dict[str, Any] = None,
                 connectArgs: Dict[str, Any] = None,
                 name: str = None,
                 **_kwargs):
        """
            Class that manages the connection to the MQTT Broker and
            communication with the MQTT Device Manager.

            :param host: The hostname/IP of the MQTT broker.
            :param port: The port to which to connect.
            :param username: The username to use to connect to the broker,
                if required.
            :param password: The password to use to connect to the broker,
                if required.
            :param mqttKeepAlive: The number of seconds to keep the MQTT
                client connection alive.
            :param threadKeepAlive: The number of seconds to keep the
                data-reading thread alive after all `MQTTSerialPort`
                instances have closed.
            :param clientArgs: Additional arguments to be used in the
                instantiation of the `paho.mqtt.client.Client`.
            :param connectArgs: Additional arguments to be used with
                `paho.mqtt.client.Client.connect()`.
        """
        if not host:
            host = getMyIP()
        elif isinstance(host, (list, tuple)):
            host = host[0]

        self.host = host
        self.port = port
        self.name = name
        self.username = username
        self.password = password
        self.keepalive = mqttKeepAlive
        self.threadKeepAlive = threadKeepAlive
        self.clientArgs = dict(CLIENT_INIT_ARGS)
        self.connectArgs = dict(CLIENT_CONNECT_ARGS)

        self.clientArgs.update(clientArgs or {})
        self.clientArgs.setdefault('client_id', makeClientID(type(self).__name__))
        self.connectArgs.update(connectArgs or {})

        self.client: mqtt.Client = None
        self.thread: Thread = None
        self._stop = Event()
        self._ports: Dict[str, "MQTTSerialPort"] = WeakValueDictionary()

        self.setup()


    def __repr__(self):
        if self.name:
            return f'<{type(self).__name__} "{self.name}" {self.host}:{self.port}>'
        return f'<{type(self).__name__} {self.host}:{self.port}>'


    @synchronized
    def setup(self, **kwargs):
        """
            The actual initialization of a new instance. Separated from
            the constructor so it can be used to change an existing
            instance. Takes the same keyword arguments as `__init__()`.
            Arguments that are unsupplied will remain unchanged.

            This only needs to be explicitly called if changes were
            made to the arguments.
        """
        if self.client and self.client.is_connected():
            self.disconnect()
        self.host = kwargs.get('host', self.host)
        self.port = kwargs.get('port', self.port)
        self.name = kwargs.get('name', self.name)
        self.username = kwargs.get('username', self.username)
        self.password = kwargs.get('password', self.password)
        self.keepalive = kwargs.get('keepalive', self.keepalive)
        self.threadKeepAlive = kwargs.get('threadKeepAlive', self.threadKeepAlive)
        self.clientArgs = kwargs.get('clientArgs', self.clientArgs)
        self.connectArgs = kwargs.get('connectArgs', self.connectArgs)

        self.devManager = None
        self.lastUsedTime = time()


    @synchronized
    def connect(self, timeout=30):
        """
            Connect/reconnect to the MQTT Broker (if not connected), and
            (re-)start the thread (if not running).
        """
        self.lastUsedTime = time()

        if not self.client:
            logger.debug(f'instantiating {mqtt.Client}...')
            self.client = mqtt.Client(**self.clientArgs)

            self.client.on_message = self._onMessage
            self.client.on_connect = self._onConnect
            self.client.on_disconnect = self._onDisconnect
            if self.username or self.password:
                self.client.username_pw_set(self.username, self.password)

        if not self.client.is_connected():
            logger.debug(f'Attempting to connect to Broker {self.host}:{self.port}...')
            err = self.client.connect(self.host, port=self.port, **self.connectArgs)
            if err != mqtt.MQTT_ERR_SUCCESS:
                raise CommunicationError(f'Failed to connect to broker: {err!r}')

        if not self.thread or not self.thread.is_alive():
            self.thread = Thread(target=self._run, daemon=True)
            self.thread.name = f'{type(self).__name__}{self.thread.name}'
            self._stop.clear()
            self.thread.start()

        deadline = time() + timeout
        while time() < deadline:
            if self.client.is_connected():
                return
            sleep(0.01)

        raise TimeoutError('Timed out waiting for client to connect')


    @synchronized
    def disconnect(self):
        """ Disconnect from the MQTT Broker. This will close all remote
            devices' connections as well. It can be reconnected by calling
            `connect()`.
        """
        logger.debug('disconnect')
        if self.thread and self.thread.is_alive():
            self._stop.set()
            while self.thread.is_alive():
                sleep(0.1)

        if self.client and self.client.is_connected():
            self.client.disconnect()

        self._stop.clear()
        self.client = None


    @synchronized
    def addPort(self, subscriber: "MQTTSerialPort"):
        """ Connect (or reconnect) an existing `MQTTSerialPort` to the
            client. To create a new virual serial port, use `newPort()`.
        """
        self.lastUsedTime = time()

        if subscriber.readTopic is None:
            # A write-only port, no additional setup.
            return

        if subscriber not in self._ports.values():
            self._ports[subscriber.readTopic] = subscriber

        result, _mid = self.client.subscribe(subscriber.readTopic,
                                             qos=subscriber.qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f'Error subscribing to {subscriber.readTopic!r}: '
                         f'{result!r}')
        else:
            logger.debug(f'Subscribed to {subscriber.readTopic!r}')


    @synchronized
    def removePort(self, subscriber: "MQTTSerialPort"):
        """ Disconnect an `MQTTSerialPort` from the client.
        """
        self._ports.pop(subscriber.readTopic, None)
        if self.client and self.client.is_connected():
            self.client.unsubscribe(subscriber.readTopic)


    @synchronized
    def _publishSubscriber(self, subscriber: "MQTTSerialPort", message: bytes):
        """ Send an MQTT message containing the contents of a call to
            `MQTTSerialPort.write()`
        """
        logger.debug(f'publishing {len(message)} bytes to topic {subscriber.writeTopic}')
        if not subscriber.writeTopic:
            raise IOError('Port is read-only')

        self.connect()
        info = self.client.publish(subscriber.writeTopic, bytes(message),
                                   qos=subscriber.qos)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f'Error publishing to virtual serial: {info.rc!r}')
            return
        try:
            info.wait_for_publish(1.0)
        except RuntimeError as err:
            logger.error(f'Error waiting for response to publishing to virtual serial: '
                         f'{err!r}')


    def _onMessage(self, _client, _userdata, message):
        """ MQTT event handler for messages.
        """
        logger.debug(f'received {len(message.payload)} bytes on {message.topic}')
        if message.topic in self._ports:
            self.lastUsedTime = time()
            self._ports[message.topic].append(message.payload)
        else:
            logger.debug(f'Message from unknown topic: {message.topic}')


    # noinspection PyUnusedLocal
    def _onConnect(self, client, userdata, disconnect_flags, reason_code, properties):
        """ MQTT event handler called when the client connects.
        """
        logger.debug(f'Connected to MQTT broker {client.host}:{client.port}'
                     f' ({reason_code.getName()})')
        for s in self._ports.values():
            if s.readTopic:
                self.addPort(s)


    # noinspection PyUnusedLocal
    def _onDisconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        """ MQTT event handler called when the client disconnects.
        """
        logger.debug(f'Disconnected from MQTT broker {client.host}:{client.port}'
                     f' ({reason_code.getName()})')
        pass


    def _run(self):
        """ Main thread loop.
        """
        while not self._stop.is_set():
            self.client.loop()
            if not self._ports and time() - self.lastUsedTime > self.threadKeepAlive:
                break
            sleep(0.01)


    def newPort(self,
            read: Optional[str] = None,
            write: Optional[str] = None,
            timeout: Optional[float] = None,
            write_timeout: Optional[float] = None,
            maxsize: int = 1024 * 16,
            qos: int = 1) -> "MQTTSerialPort":
        """
            Create a new virtual port for Serial-over-MQTT. Using this method
            is recommended over directly instantiating an `MQTTSerialPort`.

            :param read: The MQTT topic serving as RX. Can be `None` if the
                port is only written to.
            :param write: The MQTT topic serving as TX. Can be `None` if the
                port is only read from.
            :param timeout: Timeout (seconds) for port reads.
            :param write_timeout: Timeout (seconds) for port writes.
            :param maxsize: The maximum size of the read buffer.
            :param qos: MQTT quality of service for writes.
        """
        self.connect()
        if read in self._ports:
            port = self._ports[read]
            logger.debug(f'newPort(): returning existing port, '
                         'read={port.readTopic} write={port.writeTopic}')

        else:
            logger.debug(f'newPort(): creating new serial port, {read=} {write=}')
            port = MQTTSerialPort(self, read=read, write=write,
                                  timeout=timeout, write_timeout=write_timeout,
                                  maxsize=maxsize, qos=qos)

        self.addPort(port)
        return port


    def _getDevManager(self):
        """ Get or create a special `Recorder` instance representing the
            connection to the MQTT Device Manager.
        """
        # Imported here to avoid circular references.
        # I don't like doing this, but I think this case is okay.
        from ..base import Recorder

        if self.devManager:
            return self.devManager

        logger.debug("Instantiating new Device Manager 'Recorder'")
        self.devManager = Recorder(None)
        self.devManager._sn, self.devManager._snInt = 'manager', 0
        self.devManager.command = MQTTCommandInterface(self.devManager, self)
        try:
            self.devManager.command.ping()
        except (TimeoutError, ConnectionError):
            raise ConnectionError('Could not connect to remote Device Manager')

        return self.devManager


    def getDeviceInfo(self,
                      timeout: Union[int, float] = 10.0,
                      managerTimeout: Optional[int] = None,
                      callback: Optional[Callable] = None) -> List[Dict[str, Any]]:
        """
        Get a list of DEVINFO data for active devices from the MQTT Device
        Manager.

        :param timeout: Time (in seconds) to wait for a response from the
            Device Manager before raising a `DeviceTimeout` exception. `None`
            or -1 will wait indefinitely.
        :param managerTimeout: A value (in seconds) that overrides the remote
            Device Manager's timeout that excludes inactive devices. 0 will
            return all devices, regardless of how long it has been since they
            reported to the Device Manager.
        :param callback: A function to call each response-checking cycle. If
            the callback returns `True`, the wait for a response will be
            cancelled. The callback function requires no arguments.
        """
        devman = self._getDevManager()

        try:
            cmd = {'EBMLCommand': {'GetDeviceList': {}}}
            if managerTimeout is not None:
                cmd['EBMLCommand']['GetDeviceList']['Timeout'] = managerTimeout
            response = devman.command._sendCommand(cmd, timeout=timeout, callback=callback)
            if not response['DeviceList']:
                return []
            return response['DeviceList']['DeviceListItem']

        except KeyError as err:
            raise DeviceError(f"Manager response did not contain {err.args[0]}")


    def getDevices(self,
                   known: Optional[Dict[int, "Recorder"]] = None,
                   timeout: Union[int, float] = 10.0,
                   managerTimeout: Optional[int] = None,
                   callback: Optional[Callable] = None) -> List["Recorder"]:
        """
            Get a list of data recorder objects from the MQTT broker.

            :param known: A dictionary of known `Recorder` instances, keyed by
                device serial number.
            :param timeout: Time (in seconds) to wait for a response from the
                Device Manager before raising a `DeviceTimeout` exception. `None`
                or -1 will wait indefinitely.
            :param managerTimeout: A value (in seconds) that overrides the remote
                Device Manager's timeout that excludes inactive devices. 0 will
                return all devices, regardless of how long it has been since they
                reported to the Device Manager.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function
                requires no arguments.
        """
        # Imported here to avoid circular references.
        # I don't like doing this, but I think this case is okay.
        from .. import _module_busy, RECORDER_TYPES

        with _module_busy:
            known = {} if known is None else known
            devices = []
            items = self.getDeviceInfo(timeout, managerTimeout, callback)

            for n, listItem in enumerate(items):
                try:
                    sn = listItem['SerialNumber']
                    if sn in known:
                        devices.append(known[sn])
                        continue

                    info = bytes(listItem['GetInfoResponse']['InfoPayload'])
                    for devtype in RECORDER_TYPES:
                        if devtype._isRecorder(info):
                            device = devtype('remote', devinfo=info)
                            device.command = MQTTCommandInterface(device, self)
                            device._devinfo = MQTTDeviceInfo(device)
                            devices.append(device)
                            break
                except KeyError as err:
                    logger.error(f'getRemoteDevices(): DeviceListItem {n} from Manager '
                                 f'did not contain {err.args[0]}, continuing')

        return devices


class MQTTSerialPort(SimSerialPort):
    """
    A virtual serial port, communicating over MQTT. Instances are created and
    managed by `MQTTConnectionManager`.
    """

    def __init__(self,
                 manager: MQTTConnectionManager,
                 read: Optional[str] = None,
                 write: Optional[str] = None,
                 timeout: Optional[float] = None,
                 write_timeout: Optional[float] = None,
                 maxsize: int = 1024 * 16,
                 qos: int = 1):
        """
            A virtual serial port, communicating over MQTT. For convenience,
            using `MQTTConnectionManager.newPort()` is recommended over
            explicitly instantiating a `MQTTSerialPort` 'manually.'

            :param manager: The port's supporting `MQTTConnectionManager`.
            :param read: The MQTT topic serving as RX. Can be `None` if the
                port is only read from.
            :param write: The MQTT topic serving as TX. Can be `None` if the
                port is only written to.
            :param timeout: Timeout (seconds) for port reads.
            :param write_timeout: Timeout (seconds) for port writes.
            :param maxsize: The maximum size of the read buffer.
            :param qos: MQTT quality of service for writes.
        """
        self.readTopic = read
        self.writeTopic = write
        self.qos = qos
        self.manager = manager
        super().__init__(timeout=timeout, write_timeout=write_timeout, maxsize=maxsize)


    def __del__(self):
        try:
            self.manager.removePort(self)
        except (AttributeError, IOError, RuntimeError):
            pass


    @synchronized
    def append(self, data: bytes):
        """
            Add data to the end of the read buffer. Intended to be called
            from another thread.
        """
        self.buffer.extend(data)


    def read(self, size: int = 1) -> bytes:
        """
        Read size bytes from the virtual serial port. If a timeout is set it
        may return less characters as requested. With no timeout it will block
        until the requested number of bytes is read.
        """
        self.manager.lastUsedTime = time()
        return super().read(size)


    def write(self, data: bytes) -> int:
        """
            Write to the virtual serial port (if allowed).
        """
        if not self.is_open:
            logger.error('write() failed: port not open')
            raise PortNotOpenError()
        if self.writeTopic:
            self.manager._publishSubscriber(self, data)
            return len(data)
        raise TypeError('No write topic specified, port is read-only.')


# ===========================================================================
#
# ===========================================================================

class MQTTCommandInterface(SerialCommandInterface):
    """
    A mechanism for sending commands to a remote recorder over MQTT via a
    virtual serial port.

    :ivar status: The last reported device status. Not available on all
        interface types.
    :ivar make_crc: If `True`, generate CRCs for outgoing packets.
    :ivar ignore_crc: If `True`, ignore the CRC on response packets.
    """

    # Default maximum encoded command length (bytes). `None` is no limit.
    DEFAULT_MAX_COMMAND_SIZE = None


    def __init__(self,
                 device: 'Recorder',
                 manager: MQTTConnectionManager,
                 make_crc: bool = True,
                 ignore_crc: bool = False,
                 **kwargs):
        """
            Constructor.

            :param device: The Recorder to which to interface.
            :param manager: The `MQTTConnectionManager` to manage the port.
            :param make_crc: If `True`, generate CRCs for outgoing packets.
            :param ignore_crc: If `True`, ignore the CRC on response packets.

            If additional keyword arguments are provided, they will be used
            when opening the serial port.
        """
        self.manager = manager
        super().__init__(device, make_crc=make_crc, ignore_crc=ignore_crc, **kwargs)


    def getSerialPort(self,
                      reset: bool = False,
                      timeout: Union[int, float] = 1,
                      kwargs: Optional[Dict[str, Any]] = None) -> MQTTSerialPort:
        """
            Create a virtual serial connection through the MQTT broker for commands
            and responses.

            :param reset: If `True`, reset the virual serial connection if already
                open. Primarily for compatibility with `SerialCommandInterface`.
            :param timeout: Time (in seconds) to get the serial port.
            :param kwargs: Additional keyword arguments to be used when opening
                the port.
            :return: A `MQTTSerialPort` instance.
        """
        kwargs = kwargs or {}
        if reset and self.port:
            self.port.close()
            self.port = None
        if not self.port:
            if self.device.serialInt:
                sn = f'{self.device.serialInt:08d}'
            else:
                # Special serial number string (e.g., 'manager')
                sn = str(self.device.serial)
            self.port = self.manager.newPort(write=COMMAND_TOPIC.format(sn=sn),
                                        read=RESPONSE_TOPIC.format(sn=sn),
                                        timeout=timeout,
                                        write_timeout=timeout,
                                        **kwargs)
        self.port.open()
        return self.port


    def _setInfo(self,
                 infoIdx: int,
                 payload: Union[bytearray, bytes],
                 timeout: Union[int, float] = 10,
                 interval: float = .25,
                 callback: Optional[Callable] = None):
        """ Write device system information. This method is called indirectly
            by methods in `Recorder`.

            :param infoIdx: The index of the information to write.
            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
                `None` or -1 will wait indefinitely.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will
                be cancelled. The callback function should require no arguments.
        """
        # Note: `LockID` and `CommandIdx` are explicitly added to ensure they
        #   come before the `InfoPayload` in the command dict.
        cmd = {
            'EBMLCommand': {
                'LockID': None,  # will be set in _sendCommand
                'CommandIdx': None,  # will be set in _sendCommand
                'SetInfo': {
                    'InfoIndex': infoIdx,
                    'InfoPayload': payload}
            }
        }

        self._sendCommand(cmd,
                          response=True,
                          timeout=timeout,
                          lock=True,
                          index=True,
                          callback=callback)

        return True
