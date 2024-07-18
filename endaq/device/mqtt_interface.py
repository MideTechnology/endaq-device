from logging import getLogger
from threading import Event, RLock, Thread
from time import sleep, time
from typing import Any, Dict, Optional, Union

from .client import synchronized
from .command_interfaces import SerialCommandInterface
from .simserial import SimSerialPort

import paho.mqtt.client as mqtt

logger = getLogger(__name__)

# Temporary. For testing.
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
KEEP_ALIVE_INTERVAL = 60*60  #: MQTT client 'keep alive' time

THREAD_KEEP_ALIVE_INTERVAL = 60 * 5  #: Thread 'keep alive' time if there are no connections


class MQTTSerialClient:
    """
    Class that manages the MQTT Broker connection for virtual serial ports
    over MQTT. This should not be instantiated directly; use `initMQTT()`.

    This class is effectively a singleton (although not enforced). Access
    the singleton instance via `getSerialClient`.
    """

    _instance: Optional["MQTTSerialClient"] = None
    _class_lock = RLock()

    def __init__(self):
        """ Class that manages the MQTT Broker connection for virtual
            serial ports over MQTT.

        """
        self.client: mqtt.Client = None
        self.thread: Thread = None
        self._stop = Event()
        self.subscribers: Dict[str, "MQTTSerialPort"] = {}
        self.host = None
        self.port = MQTT_PORT
        self.keepalive = KEEP_ALIVE_INTERVAL
        self.threadKeepAlive = THREAD_KEEP_ALIVE_INTERVAL


    def setup(self,
              host: str = None,
              port: int = MQTT_PORT,
              mqttKeepAlive: int = KEEP_ALIVE_INTERVAL,
              threadKeepAlive: int = THREAD_KEEP_ALIVE_INTERVAL,
              clientArgs: Dict[str, Any] = None,
              connectArgs: Dict[str, Any] = None):
        """ The actual initialization of a new instance. Separated from
            the constructor so it can be used to change an existing
            instance.
        """
        self.disconnect()
        self.client: mqtt.Client = None
        self._stop.clear()
        self.host = host
        self.port = port
        self.keepalive = mqttKeepAlive
        self.threadKeepAlive = threadKeepAlive
        self.clientArgs = clientArgs or {}
        self.connectArgs = connectArgs or {}

        self.lastUsedTime = time()


    @synchronized
    def connect(self):
        """ Connect/reconnect to the MQTT Broker (if not connected), and
            (re-)start the thread (if not running).
        """
        if not self.client:
            self.client = mqtt.Client(**self.clientArgs)

        if not self.client.is_connected():
            self.client.connect(self.host, port=self.port, **self.connectArgs)
            self.client.on_message = self.onMessage
            self.client.on_publish = self.onPublish
            self.client.on_disconnect = self.onDisconnect
            for s in self.subscribers:
                self.client.subscribe(s, qos=1)

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

        self.client = None


    @synchronized
    def add(self, subscriber: "MQTTSerialPort"):
        if subscriber.receiveTopic is None:
            # A write-only port
            return

        self.connect()
        self.subscribers[subscriber.receiveTopic] = subscriber
        self.client.subscribe(subscriber.receiveTopic, qos=1)


    @synchronized
    def remove(self, subscriber: "MQTTSerialPort"):
        self.subscribers.pop(subscriber.receiveTopic, None)
        if self.client and self.client.is_connected():
            self.client.unsubscribe(subscriber.receiveTopic)


    def onMessage(self, _client, _userdata, message):
        if message.topic in self.subscribers:
            self.lastUsedTime = time()
            self.subscribers[message.topic].append(message.payload)
        else:
            logger.debug(f'Message from unknown topic: {message.topic}')


    def onPublish(self, _client, _userdata, _rc):
        self.lastUsedTime = time()


    def onDisconnect(self, _client, _userdata, _rc):
        logger.debug('Disconnected from MQTT broker')
        pass


    def run(self):
        while not self._stop.is_set():
            self.client.loop()
            if not self.subscribers and time() - self.lastUsedTime > self.keepalive:
                break
            sleep(0.01)


class MQTTSerialPort(SimSerialPort):

    def __init__(self,
                 send_topic: str,
                 receive_topic: str,
                 timeout: Optional[float] = None,
                 write_timeout: Optional[float] = None,
                 maxsize: int = 1024 * 16):
        self.sendTopic = send_topic
        self.receiveTopic = receive_topic
        self.client = getSerialClient()
        self.client.add(self)
        super().__init__(timeout=timeout, write_timeout=write_timeout, maxsize=maxsize)


    @synchronized
    def open(self):
        self.client.add(self)
        return super().open()


    @synchronized
    def close(self):
        self.client.remove(self)
        return super().close()


    @synchronized
    def append(self, data: bytes):
        self.buffer.extend(data)


    def write(self, data: bytes):
        self.client.client.publish(self.sendTopic, data, qos=1)


# ===========================================================================
#
# ===========================================================================

class MQTTCommandInterface(SerialCommandInterface):

    def __init__(self,*args, **kwargs):
        self.statePort = None
        super().__init__(*args, **kwargs)


    def getSerialPort(self,
                      reset: bool = False,
                      timeout: Union[int, float] = 1,
                      kwargs: Optional[Dict[str, Any]] = None) -> MQTTSerialPort:
        if not self.port:
            sn = str(self.device.serial).lstrip('SWH0')
            self.port = MQTTSerialPort(f'endaq/{sn}/control/response',
                                       f'endaq/{sn}/control/command',
                                       timeout=timeout,
                                       write_timeout=timeout)
        return self.port


    def getStatePort(self,
                     reset: bool = False,
                     timeout: Union[int, float] = 1,
                     kwargs: Optional[Dict[str, Any]] = None) -> MQTTSerialPort:
        if not self.statePort:
            sn = str(self.device.serial).lstrip('SWH0')
            self.statePort = MQTTSerialPort(None,
                                            f'endaq/{sn}/control/state',
                                            timeout=timeout,
                                            write_timeout=timeout)
        return self.statePort



# ===========================================================================
#
# ===========================================================================

def initMQTT(host: str = MQTT_BROKER,
             port: int = MQTT_PORT,
             mqttKeepAlive: int = KEEP_ALIVE_INTERVAL,
             threadKeepAlive: int = THREAD_KEEP_ALIVE_INTERVAL,
             clientArgs: Dict[str, Any] = None,
             connectArgs: Dict[str, Any] = None):

    with MQTTSerialClient._class_lock:
        if MQTTSerialClient._instance is None:
            MQTTSerialClient._instance = MQTTSerialClient()

        MQTTSerialClient._instance.setup(host,port,
                            mqttKeepAlive=mqttKeepAlive,
                            threadKeepAlive=threadKeepAlive,
                            clientArgs=clientArgs,
                            connectArgs=connectArgs)


def getSerialClient():
    with MQTTSerialClient._class_lock:
        if MQTTSerialClient._instance:
            return MQTTSerialClient._instance
        raise ValueError('initMQTT() must be called first!')
