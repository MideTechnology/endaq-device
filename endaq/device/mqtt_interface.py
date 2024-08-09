import logging
from threading import Event, Thread
from time import sleep, time
from typing import Any, Callable, Dict, List, Optional, Union
from weakref import WeakValueDictionary

from .client import synchronized
from .command_interfaces import SerialCommandInterface
from .devinfo import MQTTDeviceInfo
from .exceptions import CommunicationError, DeviceError
from .simserial import SimSerialPort

import paho.mqtt.client as mqtt
from serial import PortNotOpenError

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .base import Recorder

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ===========================================================================
#
# ===========================================================================

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
KEEP_ALIVE_INTERVAL = 60*60  #: MQTT client 'keep alive' time (seconds)
THREAD_KEEP_ALIVE_INTERVAL = 60 * 5  #: Thread 'keep alive' time (seconds) if there are no connections

# Default keyword arguments for `paho.mqtt.client.Client.__init__()` and `.connect()`
CLIENT_INIT_ARGS = (('callback_api_version', mqtt.CallbackAPIVersion.VERSION2),)
CLIENT_CONNECT_ARGS = ()

COMMAND_TOPIC = "endaq/{sn}/control/command"
RESPONSE_TOPIC = "endaq/{sn}/control/response"
STATE_TOPIC = "endaq/{sn}/control/state"

_MANAGER_INSTANCE = None  #: A default instance of `MQTTSerialManager`


# ===========================================================================
#
# ===========================================================================

class MQTTSerialManager:
    """
    Class that manages the MQTT Broker connection for virtual serial ports
    over MQTT. Generally, there will be only one instance of this class,
    as it handles multiple virtual serial ports.
    """

    def __init__(self,
              host: str= MQTT_BROKER,
              port: int = MQTT_PORT,
              username: Optional[str] = None,
              password: Optional[str] = None,
              mqttKeepAlive: int = KEEP_ALIVE_INTERVAL,
              threadKeepAlive: int = THREAD_KEEP_ALIVE_INTERVAL,
              clientArgs: Dict[str, Any] = None,
              connectArgs: Dict[str, Any] = None):
        """
            Class that manages the MQTT Broker connection for virtual
            serial ports over MQTT.

            :param host: The hostname of the MQTT broker.
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
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.keepalive = mqttKeepAlive
        self.threadKeepAlive = threadKeepAlive
        self.clientArgs = dict(CLIENT_INIT_ARGS)
        self.connectArgs = dict(CLIENT_CONNECT_ARGS)

        self.clientArgs.update(clientArgs or {})
        self.connectArgs.update(connectArgs or {})

        self.client: mqtt.Client = None
        self.thread: Thread = None
        self._stop = Event()
        self.subscribers: Dict[str, "MQTTSerialPort"] = WeakValueDictionary()

        self.setup()


    @synchronized
    def setup(self,
              **kwargs):
        """
            The actual initialization of a new instance. Separated from
            the constructor so it can be used to change an existing
            instance. Takes the same keyword arguments as `__init__()`.
            Arguments that are unsupplied will remain unchanged.
        """
        self.disconnect()
        self.host = kwargs.get('host', self.host)
        self.port = kwargs.get('port', self.port)
        self.username = kwargs.get('username', self.username)
        self.password = kwargs.get('password', self.password)
        self.keepalive = kwargs.get('keepalive', self.keepalive)
        self.threadKeepAlive = kwargs.get('threadKeepAlive', self.threadKeepAlive)
        self.clientArgs = kwargs.get('clientArgs', self.clientArgs)
        self.connectArgs = kwargs.get('connectArgs', self.connectArgs)

        self.lastUsedTime = time()


    @synchronized
    def connect(self):
        """
            Connect/reconnect to the MQTT Broker (if not connected), and
            (re-)start the thread (if not running).
        """
        if not self.client:
            logger.debug(f'instantiating {mqtt.Client}...')
            self.client = mqtt.Client(**self.clientArgs)

            self.client.on_message = self.onMessage
            self.client.on_disconnect = self.onDisconnect
            if self.username or self.password:
                self.client.username_pw_set(self.username, self.password)

        if not self.client.is_connected():
            logger.debug('connecting...')
            err = self.client.connect(self.host, port=self.port, **self.connectArgs)
            if err != mqtt.MQTT_ERR_SUCCESS:
                raise CommunicationError(f'Failed to connect to broker: {err!r}')

            for s in self.subscribers.values():
                if s.readTopic:
                    self.add(s)

        if not self.thread or not self.thread.is_alive():
            self.thread = Thread(target=self.run, daemon=True)
            self.thread.name = f'{type(self).__name__}{self.thread.name}'
            self._stop.clear()
            self.thread.start()

        self.lastUsedTime = time()


    @synchronized
    def disconnect(self):
        if self.thread and self.thread.is_alive():
            self._stop.set()
            while self.thread.is_alive():
                sleep(0.1)

        if self.client and self.client.is_connected():
            # self.client.unsubscribe('#')
            self.client.disconnect()

        self._stop.clear()
        self.client = None


    @synchronized
    def add(self, subscriber: "MQTTSerialPort"):
        """ Connect a `MQTTSerialPort` to the client.
        """
        if subscriber.readTopic is None:
            # A write-only port, no additional setup.
            return

        if subscriber not in self.subscribers.values():
            self.subscribers[subscriber.readTopic] = subscriber

        result, _mid = self.client.subscribe(subscriber.readTopic, qos=subscriber.qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f'Error subscribing to {subscriber.readTopic!r}: {result!r}')
        else:
            logger.debug(f'Subscribed to {subscriber.readTopic!r}')


    @synchronized
    def remove(self, subscriber: "MQTTSerialPort"):
        """ Disconnect an `MQTTSerialPort` from the client.
        """
        self.subscribers.pop(subscriber.readTopic, None)
        if self.client and self.client.is_connected():
            self.client.unsubscribe(subscriber.readTopic)


    @synchronized
    def publishSubscriber(self, subscriber: "MQTTSerialPort", message: bytes):
        """ Send an MQTT message containing the contents of a call to
            `MQTTSerialPort.write()`
        """
        logger.debug(f'publishing {len(message)} bytes to topic {subscriber.writeTopic}')
        if not subscriber.writeTopic:
            raise IOError('Port is read-only')

        self.lastUsedTime = time()
        self.connect()
        info = self.client.publish(subscriber.writeTopic, bytes(message), qos=subscriber.qos)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f'Error publishing to virtual serial: {info.rc!r}')
            return
        try:
            info.wait_for_publish(1.0)
        except RuntimeError as err:
            logger.error(f'Error waiting for response to publishing to virtual serial: {err!r}')


    def onMessage(self, _client, _userdata, message):
        """ MQTT event handler for messages.
        """
        logger.debug(f'received {len(message.payload)} bytes on {message.topic}')
        if message.topic in self.subscribers:
            self.lastUsedTime = time()
            self.subscribers[message.topic].append(message.payload)
        else:
            logger.debug(f'Message from unknown topic: {message.topic}')


        """ MQTT event handler called when messages are published.
        """
        self.lastUsedTime = time()


    def onDisconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        """ MQTT event handler called when the client disconnects.
        """
        logger.debug(f'Disconnected from MQTT broker {reason_code=!r}')
        pass


    def run(self):
        """ Main thread loop.
        """
        while not self._stop.is_set():
            self.client.loop()
            if not self.subscribers and time() - self.lastUsedTime > self.keepalive:
                break
            sleep(0.01)


    def stop(self):
        self._stop.set()
        while self.thread and self.thread.is_alive():
            sleep(0.1)


    def new(self,
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
        if read in self.subscribers:
            port = self.subscribers[read]
            logger.debug(f'new(): returning existing port, read={port.readTopic} write={port.writeTopic}')
            return port

        logger.debug(f'new(): creating new serial port, {read=} {write=}')
        port = MQTTSerialPort(self, read=read, write=write,
                              timeout=timeout, write_timeout=write_timeout,
                              maxsize=maxsize, qos=qos)

        self.add(port)
        return port


class MQTTSerialPort(SimSerialPort):
    """
    A virtual serial port, communicating over MQTT.
    """

    def __init__(self,
                 manager: MQTTSerialManager,
                 read: Optional[str] = None,
                 write: Optional[str] = None,
                 timeout: Optional[float] = None,
                 write_timeout: Optional[float] = None,
                 maxsize: int = 1024 * 16,
                 qos: int = 1):
        """
            A virtual serial port, communicating over MQTT. For convenience,
            using `MQTTSerialManager.new()` is recommended over explicitly
            instantiating a `MQTTSerialPort` 'manually.'

            :param manager: The port's supporting `MQTTSerialManager`.
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


    @synchronized
    def close(self):
        self.manager.remove(self)
        return super().close()


    @synchronized
    def append(self, data: bytes):
        """
            Add data to the end of the read buffer. Intended to be called
            from another thread.
        """
        self.buffer.extend(data)


    def write(self, data: bytes) -> int:
        """
            Write to the virtual serial port (if allowed).
        """
        if not self.is_open:
            logger.error('write() failed: port not open')
            raise PortNotOpenError()
        if self.writeTopic:
            self.manager.publishSubscriber(self, data)
            return len(data)
        raise TypeError('No write topic specified, port is read-only.')


# ===========================================================================
#
# ===========================================================================

class MQTTCommandInterface(SerialCommandInterface):
    """
    A mechanism for sending commands to a recorder over MQTT via a virtual
    serial port.

    :ivar status: The last reported device status. Not available on all
        interface types.
    :ivar make_crc: If `True`, generate CRCs for outgoing packets.
    :ivar ignore_crc: If `True`, ignore the CRC on response packets.
    """

    def __init__(self,
                 device: 'Recorder',
                 client: MQTTSerialManager,
                 make_crc: bool = True,
                 ignore_crc: bool = False,
                 **kwargs):
        """
            Constructor.

            :param device: The Recorder to which to interface.
            :param client: The `MQTTSerialManager` to manage the port.
            :param make_crc: If `True`, generate CRCs for outgoing packets.
            :param ignore_crc: If `True`, ignore the CRC on response packets.

            If additional keyword arguments are provided, they will be used
            when opening the serial port.
        """
        self.client = client
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
            sn = str(self.device.serial).lstrip('SWH0')
            self.port = self.client.new(write=COMMAND_TOPIC.format(sn=sn),
                                        read=RESPONSE_TOPIC.format(sn=sn),
                                        timeout=timeout,
                                        write_timeout=timeout,
                                        **kwargs)
        self.port.open()
        return self.port


# ===========================================================================
#
# ===========================================================================

def getRemoteDevices(known: Optional[Dict[int, "Recorder"]] = None,
                     client: Optional[MQTTSerialManager] = None,
                     timeout: Union[int, float] = 10.0,
                     managerTimeout: Optional[int] = None,
                     callback: Optional[Callable] = None) -> List["Recorder"]:
    """ Get a list of data recorder objects from the MQTT broker.

        :param known: A dictionary of known `Recorder` instances, keyed by
            device serial number.
        :param client: An `MQTTSerialManager` instance, if the client requires
            specific arguments or preparation. Defaults to a client with
            the default arguments.
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
    global _MANAGER_INSTANCE
    client = client or _MANAGER_INSTANCE

    if not client:
        client = _MANAGER_INSTANCE = MQTTSerialManager()

    # Imported here to avoid circular references.
    # I don't like doing this, but I think this case is okay.
    from . import _module_busy, RECORDER_TYPES, Recorder

    if known is None:
        known = {}

    devices = []

    # Dummy recorder and command interface to retrieve DEVINFO
    fake = Recorder(None)
    fake._sn, fake._snInt = 'manager', 0
    fake.command = MQTTCommandInterface(fake, client)

    with _module_busy:
        try:
            cmd = {'EBMLCommand': {'GetDeviceList': {}}}
            if managerTimeout is not None:
                cmd['EBMLCommand']['GetDeviceList']['Timeout'] = managerTimeout
            response = fake.command._sendCommand(cmd, timeout=timeout, callback=callback)
            if not response['DeviceList']:
                return devices
            items = response['DeviceList']['DeviceListItem']

        except KeyError as err:
            raise DeviceError(f"Manager response did not contain {err.args[0]}")

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
                        device.command = MQTTCommandInterface(device, client)
                        device._devinfo = MQTTDeviceInfo(device)
                        devices.append(device)
                        break
            except KeyError as err:
                logger.error(f'DeviceListItem {n} from Manager did not contain {err.args[0]}')

    return devices
