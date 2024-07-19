from logging import getLogger
from threading import Event, RLock, Thread
from time import sleep, time
from typing import Any, Dict, Optional, Union, TYPE_CHECKING

from .client import synchronized
from .command_interfaces import SerialCommandInterface
from .simserial import SimSerialPort

import paho.mqtt.client as mqtt
from serial import PortNotOpenError

if TYPE_CHECKING:
    from .base import Recorder

logger = getLogger(__name__)

# Temporary. For testing.
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
KEEP_ALIVE_INTERVAL = 60*60  #: MQTT client 'keep alive' time

THREAD_KEEP_ALIVE_INTERVAL = 60 * 5  #: Thread 'keep alive' time if there are no connections


class MQTTSerialClient:
    """
    Class that manages the MQTT Broker connection for virtual serial ports
    over MQTT. Generally, there will be only one instance of this class,
    as it handles multiple virtual serial ports.
    """

    def __init__(self,
              host: str,
              port: int = MQTT_PORT,
              mqttKeepAlive: int = KEEP_ALIVE_INTERVAL,
              threadKeepAlive: int = THREAD_KEEP_ALIVE_INTERVAL,
              clientArgs: Dict[str, Any] = None,
              connectArgs: Dict[str, Any] = None):
        """
            Class that manages the MQTT Broker connection for virtual
            serial ports over MQTT.

            :param host: The hostname of the MQTT broker.
            :param port: The port to which to connect.
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
        self.keepalive = mqttKeepAlive
        self.threadKeepAlive = threadKeepAlive
        self.clientArgs = clientArgs or {}
        self.connectArgs = connectArgs or {}

        self.client: mqtt.Client = None
        self.thread: Thread = None
        self._stop = Event()
        self.subscribers: Dict[str, "MQTTSerialPort"] = {}

        self.setup(host, port,
                   mqttKeepAlive=mqttKeepAlive, threadKeepAlive=threadKeepAlive,
                   clientArgs=clientArgs, connectArgs=connectArgs)


    def setup(self,
              host: str = None,
              port: int = MQTT_PORT,
              mqttKeepAlive: int = KEEP_ALIVE_INTERVAL,
              threadKeepAlive: int = THREAD_KEEP_ALIVE_INTERVAL,
              clientArgs: Dict[str, Any] = None,
              connectArgs: Dict[str, Any] = None):
        """
            The actual initialization of a new instance. Separated from
            the constructor so it can be used to change an existing
            instance.

            :param host: The hostname of the MQTT broker.
            :param port: The port to which to connect.
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
        self.disconnect()
        self.host = host or self.host
        self.port = port or self.port
        self.keepalive = mqttKeepAlive if mqttKeepAlive is not None else self.keepalive
        self.threadKeepAlive = threadKeepAlive if threadKeepAlive is not None else self.threadKeepAlive
        self.clientArgs = clientArgs or {}
        self.connectArgs = connectArgs or {}

        self.lastUsedTime = time()


    @synchronized
    def connect(self):
        """
            Connect/reconnect to the MQTT Broker (if not connected), and
            (re-)start the thread (if not running).
        """
        if not self.client:
            self.client = mqtt.Client(**self.clientArgs)

        if not self.client.is_connected():
            self.client.connect(self.host, port=self.port, **self.connectArgs)
            self.client.on_message = self.onMessage
            self.client.on_publish = self.onPublish
            self.client.on_disconnect = self.onDisconnect
            for sn, s in self.subscribers:
                if s.readTopic:
                    self.client.subscribe(s.readTopic, qos=s.qos)

        if not self.thread.is_alive():
            self.thread = Thread(target=self.run, daemon=True)
            self.thread.name = self.thread.name.replace('Thread', type(self).__name__)
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
            self.client.unsubscribe('#')
            self.client.disconnect()

        self._stop.clear()
        self.client = None


    @synchronized
    def add(self, subscriber: "MQTTSerialPort"):
        """ Connect a `MQTTSerialPort` to the client.
        """
        if subscriber.readTopic is None:
            # A write-only port
            return

        self.connect()
        self.subscribers[subscriber.readTopic] = subscriber
        self.client.subscribe(subscriber.readTopic, qos=subscriber.qos)


    @synchronized
    def remove(self, subscriber: "MQTTSerialPort"):
        """ Disconnect an `MQTTSerialPort` from the client.
        """
        self.subscribers.pop(subscriber.readTopic, None)
        if self.client and self.client.is_connected():
            self.client.unsubscribe(subscriber.readTopic)


    @synchronized
    def publish(self, subscriber: "MQTTSerialPort", message: bytes):
        if not subscriber.writeTopic:
            raise IOError('Port is read-only')

        self.connect()
        self.client.publish(subscriber.writeTopic, message, qos=subscriber.qos)


    def onMessage(self, _client, _userdata, message):
        """ MQTT event handler for messages.
        """
        if message.topic in self.subscribers:
            self.lastUsedTime = time()
            self.subscribers[message.topic].append(message.payload)
        else:
            logger.debug(f'Message from unknown topic: {message.topic}')


    def onPublish(self, _client, _userdata, _rc):
        """ MQTT event handler called when messages are published.
        """
        self.lastUsedTime = time()


    def onDisconnect(self, _client, _userdata, _rc):
        """ MQTT event handler called when the client disconnects.
        """
        logger.debug('Disconnected from MQTT broker')
        pass


    def run(self):
        """ Main thread loop.
        """
        while not self._stop.is_set():
            self.client.loop()
            if not self.subscribers and time() - self.lastUsedTime > self.keepalive:
                break
            sleep(0.01)


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
                port is only read from.
            :param write: The MQTT topic serving as TX. Can be `None` if the
                port is only written to.
            :param timeout: Timeout (seconds) for port reads.
            :param write_timeout: Timeout (seconds) for port writes.
            :param maxsize: The maximum size of the read buffer.
            :param qos: MQTT quality of service for writes.
        """
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
                 client: MQTTSerialClient,
                 read: Optional[str] = None,
                 write: Optional[str] = None,
                 timeout: Optional[float] = None,
                 write_timeout: Optional[float] = None,
                 maxsize: int = 1024 * 16,
                 qos: int = 1):
        """
            A virtual serial port, communicating over MQTT. For convenience,
            using `MQTTSerialClient.new()` is recommended over explicitly
            instantiating a `MQTTSerialPort` 'manually.'

            :param client: The port's supporting `MQTTSerialClient`.
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
        self.client = client
        super().__init__(timeout=timeout, write_timeout=write_timeout, maxsize=maxsize)


    @synchronized
    def close(self):
        self.client.remove(self)
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
            raise PortNotOpenError()
        if self.writeTopic:
            self.client.client.publish(self.writeTopic, data, qos=self.qos)
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
                 client: MQTTSerialClient,
                 make_crc: bool = True,
                 ignore_crc: bool = False,
                 **kwargs):
        """
            Constructor.

            :param device: The Recorder to which to interface.
            :param client: The `MQTTSerialClient` to manage the port.
            :param make_crc: If `True`, generate CRCs for outgoing packets.
            :param ignore_crc: If `True`, ignore the CRC on response packets.

            If additional keyword arguments are provided, they will be used
            when opening the serial port.
        """
        self.client = client
        self.statePort = None
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
        if reset and self.port:
            self.port.close()
            self.port = None
        if not self.port:
            sn = str(self.device.serial).lstrip('SWH0')
            self.port = self.client.new(read=f'endaq/{sn}/control/response',
                                        write=f'endaq/{sn}/control/command',
                                        timeout=timeout,
                                        write_timeout=timeout,
                                        **kwargs)
        return self.port


    def getStatePort(self,
                     reset: bool = False,
                     timeout: Union[int, float] = 1,
                     kwargs: Optional[Dict[str, Any]] = None) -> MQTTSerialPort:
        """
            Create a virtual serial connection through the MQTT broker for posting
            device status updates (used by the MQTT device manager).

            :param reset: If `True`, reset the virual serial connection if already
                open.
            :param timeout: Time (in seconds) to get the serial port.
            :param kwargs: Additional keyword arguments to be used when opening
                the port.
            :return: A `MQTTSerialPort` instance.
        """
        if reset and self.statePort:
            self.statePort.close()
            self.statePort = None
        if not self.statePort:
            sn = str(self.device.serial).lstrip('SWH0')
            self.statePort = self.client.new(write=f'endaq/{sn}/control/state',
                                             timeout=timeout,
                                             write_timeout=timeout,
                                             **kwargs)
        return self.statePort
