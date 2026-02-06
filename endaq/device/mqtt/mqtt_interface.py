"""
MQTT Interface
==============

This module handles creating a connection to an MQTT broker, and
communicating with an MQTT Device Manager. The main component in this module
is :class:`MQTTConnector`, through which MQTT-enabled `Recorder` instances are
created.

The simplest way to instantiate an `MQTTConnector` is with
:meth:`MQTTConnector.find()`, which will try to automatically connect to
an MQTT broker advertised by the :class:`MQTTDeviceManager`.
Once an instance of an `MQTTConnector` has been created, MQTT devices can
be found using the :meth:`getDevices()` method.

.. code-block:: python

    >>> from endaq.device.mqtt.mqtt_interface import MQTTConnector
    >>> con = MQTTConnector.find()

"""

from contextlib import suppress
from datetime import datetime
import logging
import os.path
from pathlib import Path
import string
from threading import Event, Thread
from time import sleep, time
from typing import Any, BinaryIO, Callable, Dict, List, Optional, Tuple, Union
from weakref import WeakValueDictionary

import paho.mqtt.client as mqtt
from serial import PortNotOpenError

from .. import (_module_busy, RECORDER_TYPES, RECORDERS,
                RECORDERS_BY_SN, RECORDER_CACHE_SIZE)

from .discovery import findBrokers, SERVICE_TYPE
from ..base import Recorder, NonRecorder
from ..command_interfaces import SerialCommandInterface
from ..devinfo import MQTTDeviceInfo
from ..exceptions import CommandError, CommunicationError, DeviceError, UnsupportedFeature
from ..response_codes import DeviceStatusCode
from ..simserial import SimSerialPort
from ..types import Filename
from ..util import getMyIP, makeClientID, synchronized

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

__all__ = ('MQTTConnector',)

# ===========================================================================
#
# ===========================================================================

MQTT_BROKER = None  # "localhost"
MQTT_PORT = 1883
KEEP_ALIVE_INTERVAL = 60  #: MQTT client 'keep alive' time (seconds)

# Default keyword arguments for `paho.mqtt.client.Client.__init__()` and `.connect()`
CLIENT_INIT_ARGS = (('callback_api_version', mqtt.CallbackAPIVersion.VERSION2),)
CLIENT_CONNECT_ARGS = (('keepalive', KEEP_ALIVE_INTERVAL),)

COMMAND_TOPIC = "endaq/{sn}/control/command"
RESPONSE_TOPIC = "endaq/{sn}/control/response"
STATE_TOPIC = "endaq/{sn}/control/state"
HEADER_TOPIC = "endaq/{sn}/header"
MEASUREMENT_TOPIC = "endaq/{sn}/measurement"

EBML_ID_BYTES = b'\x1A\x45\xDF\xA3'  # To identify `EBML` elements in stream


# ===========================================================================
#
# ===========================================================================

class MQTTConnector:
    """
    Class that manages the connection to the MQTT Broker and communication
    with the MQTT Device Manager.
    """

    def __init__(self,
                 host: str = MQTT_BROKER,
                 port: int = MQTT_PORT,
                 name: str = None,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 clientArgs: Dict[str, Any] = None,
                 connectArgs: Dict[str, Any] = None,
                 autoupdate: bool = True,
                 updateCallback: Callable = None,
                 connectCallback: Callable = None,
                 disconnectCallback: Callable = None,
                 **kwargs):
        """
        Class that manages the connection to the MQTT Broker and
        communication with the MQTT Device Manager.

        :param host: The hostname/IP of the MQTT broker. Defaults to
            the local machine. Note that ``localhost`` and ``127.0.0.1``
            are explicitly converted to the local machine's IP.
        :param port: The port to which to connect.
        :param username: The username to use to connect to the broker,
            if required.
        :param password: The password to use to connect to the broker,
            if required.
        :param clientArgs: Additional arguments to be used in the
            instantiation of the `paho.mqtt.client.Client`.
        :param connectArgs: Additional arguments to be used with
            `paho.mqtt.client.Client.connect()`.
        :param autoupdate: If `True`, known devices will have their
            status automatically updated when the `MQTTDeviceManager`
            publishes updates to its 'state' topic.
        :param updateCallback: A function to be called when a 'state'
            update is received from the `MQTTDeviceManager`. The
            function should acceptone argument, a dictionary of state
            data. This can be set later via the
            `MQTTConnector.updateCallback` attribute.
        :param connectCallback: A function to be called when the
            connection to the broker is established. The function
            should accept the same arguments as the `on_connect` handler
            of a `paho.mqtt.client.Client`. This can be set later via the
            `MQTTConnector.connectCallback` attribute.
        :param disconnectCallback: A function to be called when the
            connection to the broker is lost.  The function should
            accept the same arguments as the `on_disconnect` handler
            of a `paho.mqtt.client.Client`. This can be set later via the
            `MQTTConnector.disconnectCallback` attribute.
        """
        if not host or host in ('localhost', '127.0.0.1'):
            host = getMyIP()
        elif isinstance(host, (list, tuple)):
            host = host[0]

        self.host = host
        self.port = port
        self.name = name
        self.service = kwargs.get('serviceType', SERVICE_TYPE)
        self.username = username
        self.password = password
        self.clientArgs = dict(CLIENT_INIT_ARGS)
        self.connectArgs = dict(CLIENT_CONNECT_ARGS)
        self.autoupdate = autoupdate  # Desired state of `autoupdate`
        self.updateCallback = updateCallback
        self.connectCallback = connectCallback
        self.disconnectCallback = disconnectCallback

        self.clientArgs.update(clientArgs or {})
        self.clientArgs.setdefault('client_id', makeClientID(type(self).__name__))
        self.connectArgs.update(connectArgs or {})

        self.client: mqtt.Client = None
        self.thread: Thread = None
        self._stop = Event()
        self._ports: Dict[str, "MQTTSerialPort"] = WeakValueDictionary()
        self._subscriptions = {}

        self._streamers: Dict[str, "MQTTCommandInterface"] = {}

        self.devManager = None
        self._managerStateTopic = STATE_TOPIC.format(sn='manager')
        self.lastUsedTime = time()

        # Serial numbers to exclude from updates (e.g., devices that are also
        # USB/serial) to prevent conflicts. Not automatically populated.
        self.exclude: set[int] = set()


    @classmethod
    def find(cls, *patterns, **kwargs) -> "MQTTConnector":
        """ A convenience method for creating a new `MQTTConnector` using
            an MQTT broker discovered via mDNS. It calls
            `endaq.device.mqtt.discovery.findBrokers()` and then instantiates
            an `MQTTConnector` using the closest matching broker name. All
            keywords for both are accepted.

            :param patterns: Zero or more MQTT Broker names (multiple
                positional arguments). Glob-like wildcards may be used
                (case-sensitive). Defaults are used if no arguments are
                provided.
        """
        scantime = kwargs.pop('scantime', 2)
        timeout = kwargs.pop('timeout', 5)
        callback = kwargs.pop('callback', None)

        brokers = findBrokers(*patterns, scantime=scantime, timeout=timeout, callback=callback)
        if not brokers:
            raise NameError(f'No brokers found matching name pattern(s) {patterns!r}')

        broker = brokers[0]
        broker.update(kwargs)
        return cls(**broker)


    def __repr__(self):
        if self.name:
            return f'<{type(self).__name__} "{self.name}" {self.host}:{self.port}>'
        return f'<{type(self).__name__} {self.host}:{self.port}>'


    def subscribe(self, topic, *args, **kwargs) -> tuple[mqtt.MQTTErrorCode, Optional[int]]:
        """ Wrapper for subscribing to MQTT topics, which are stored for
            resubscribing if the broker connection changes (e.g., its IP
            changed after rebooting).
        """
        if isinstance(topic, (list, tuple)):
            for t in topic:
                self._subscriptions[t] = args, kwargs
        else:
            self._subscriptions[topic] = args, kwargs
        result, mid = self.client.subscribe(topic, *args, **kwargs)
        if result == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f'Subscribed to {topic}')
        else:
            logger.error(f'Error subscribing to "{topic}": {result!r}')
        return result, mid


    def unsubscribe(self, topic, properties=None) -> tuple[mqtt.MQTTErrorCode, Optional[int]]:
        """ Wrapper for unsubscribing to MQTT topics, which also removes
            them from the set of cached topics.
        """
        if isinstance(topic, (list, tuple)):
            for t in topic:
                self._subscriptions.pop(t, None)
        else:
            self._subscriptions.pop(topic, None)
        result, mid = self.client.unsubscribe(topic, properties)
        if result == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f'Unsubscribed to {topic}')
        else:
            logger.error(f'Error unsubscribing to "{topic}": {result!r}')
        return result, mid


    def resubscribe(self):
        """ Resubscribe to all topics currently subscribed to. For use
            after changing a broker connection (e.g., its IP changed
            after rebooting).
        """
        for topic, (args, kwargs) in list(self._subscriptions.items()):
            logger.debug(f'Resubscribing to topic {topic}')
            self.client.subscribe(topic, *args, **kwargs)

    @synchronized
    def connect(self, timeout=30):
        """
            Connect to the MQTT Broker (if not connected), and start the
            thread (if not running).
        """
        self.lastUsedTime = time()

        if not self.client:
            logger.debug(f'instantiating {mqtt.Client}...')
            self.client = mqtt.Client(**self.clientArgs)

            if self.username or self.password:
                self.client.username_pw_set(self.username, self.password)

            self.client.reconnect_delay_set()
            self.client.on_message = self._onMessage
            self.client.on_connect = self._onConnect
            self.client.on_disconnect = self._onDisconnect

        if not self.client.is_connected():
            logger.debug(f'Attempting to connect to Broker {self.host}:{self.port}...')
            err = self.client.connect(self.host, port=self.port, **self.connectArgs)
            if err != mqtt.MQTT_ERR_SUCCESS:
                raise CommunicationError(f'Failed to connect to broker: {err!r}')

        result, _mid = self.subscribe(self._managerStateTopic, qos=0)
        # if result == mqtt.MQTT_ERR_SUCCESS:
        #     self.client.message_callback_add(self._managerStateTopic, self._onMessage)

        self.client.loop_start()

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
        if self.client:
            if self.client.is_connected():
                self.client.disconnect()
            self.client.loop_stop()

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


    @synchronized
    def removePort(self, subscriber: "MQTTSerialPort"):
        """ Disconnect an `MQTTSerialPort` from the client.
        """
        self._ports.pop(subscriber.readTopic, None)
        if self.client and self.client.is_connected():
            self.unsubscribe(subscriber.readTopic)


    @synchronized
    def _publishSubscriber(self, subscriber: "MQTTSerialPort", message: bytes):
        """ Send an MQTT message containing the contents of a call to
            `MQTTSerialPort.write()`
        """
        logger.debug(f'publishing {len(message)} bytes to topic {subscriber.writeTopic}')
        if not subscriber.writeTopic:
            raise IOError('Port is read-only')

        if not self.client or not self.client.is_connected():
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


    def _onMessage(self, client, userdata, message):
        """ MQTT event handler for messages.
        """
        logger.debug(f'received {len(message.payload)} bytes on {message.topic}')

        if message.topic in self._ports:
            self.lastUsedTime = time()
            self._ports[message.topic].append(message.payload)
        elif message.topic == self._managerStateTopic:
            # Handle state messages in a separate thread to prevent the paho
            # client from blocking if a device is receiving a large response
            # to a command.
            # TODO: This is a simple implementation that may need more work
            t = Thread(target=self._onManagerState, args=(client, userdata, message), daemon=True)
            t.start()
        elif message.topic in self._streamers:
            self._streamers[message.topic]._writeStreamChunk(message.payload)
        else:
            logger.debug(f'Message from unknown topic: {message.topic}')


    def _onManagerState(self, _client, _userdata, message):
        """ MQTT event handler for ``endaq/manager/control/state`` updates.
        """
        try:
            devman = self._getDevManager()
            if not devman:
                logger.error(f'Device manager not available')
                return

            try:
                response = devman.command._decode(message.payload)['EBMLResponse']
                self._updateDeviceInfo(devman, response)
            except KeyError as err:
                logger.error(f'Device manager state message missing item: {err!r}')
                return

            if self.autoupdate:
                try:
                    deviceList = response['DeviceList']['DeviceListItem']
                    for listItem in deviceList:
                        sn = listItem.get('SerialNumber')
                        if not sn or sn in self.exclude:
                            continue
                        elif sn in RECORDERS_BY_SN:
                            self._updateDeviceInfo(RECORDERS_BY_SN[sn], listItem)
                            # TODO: Exclude unchanged devices?
                except KeyError:
                    pass

            if self.updateCallback:
                self.updateCallback(response)

        except Exception as err:
            logger.error(f'Unexpected error updating manager state: {err!r}',
                         exc_info=True)
            raise

    # noinspection PyUnusedLocal
    def _onConnect(self, client, userdata, disconnect_flags, reason_code, properties):
        """ MQTT event handler called when the client connects.
        """
        logger.debug(f'Connected to MQTT broker {client.host}:{client.port}'
                     f' ({reason_code.getName()})')
        self.resubscribe()

        if self.connectCallback:
            self.connectCallback(client, userdata, disconnect_flags, reason_code, properties)


    # noinspection PyUnusedLocal
    def _onDisconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        """ MQTT event handler called when the client disconnects.
        """
        logger.debug(f'Disconnected from MQTT broker {client.host}:{client.port}'
                     f' ({reason_code.getName()})')

        if self.disconnectCallback:
            self.disconnectCallback(client, userdata, disconnect_flags, reason_code, properties)


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
                         f'read={port.readTopic} write={port.writeTopic}')

        else:
            logger.debug(f'newPort(): creating new serial port, {read=} {write=}')
            port = MQTTSerialPort(self, read=read, write=write,
                                  timeout=timeout, write_timeout=write_timeout,
                                  maxsize=maxsize, qos=qos)

        self.addPort(port)
        return port


    @synchronized
    def _getDevManager(self):
        """ Get or create a special `Recorder` instance representing the
            connection to the MQTT Device Manager.
        """
        if self.devManager:
            return self.devManager

        logger.debug("Instantiating new Device Manager 'Recorder'")
        self.devManager = NonRecorder('remote', name="DeviceManager")
        self.devManager._sn, self.devManager._snInt = 'manager', 0
        self.devManager.command = MQTTCommandInterface(self.devManager, self)
        self.devManager._devinfo = MQTTDeviceInfo(self.devManager)

        return self.devManager


    @property
    def command(self) -> "MQTTCommandInterface":
        return self._getDevManager().command


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
            raise DeviceError(f"Manager response did not contain element {err.args[0]!r}")


    def _updateDeviceInfo(self,
                          device: "Recorder",
                          info: Dict[str, Any]):
        """
            Apply metadata and status info from from the Device Manager to a
            `Recorder`.

            :param device: The device to update.
            :param info: A dictionary of device state info, as received in
                a device's ``state`` topic or as part of a Manager's
                ``state`` update.
        """
        lastContact = info.get('LastContact', 0)
        device._lastContact = lastContact
        device._lastMeasurement = info.get('LastMeasurement', 0)
        device._lastHeader = info.get('LastHeader', 0)
        device._lastCommand = info.get('LastCommand', 0)
        device._lastCommandID = info.get('LastCommandID', None)
        device.command._setStatus(None,  # CommandResponseCode (skip for state update)
                                  None,  # CommandResponseMessage (skip for state update)
                                  info.get('DeviceStatusCode'),
                                  info.get('DeviceStatusMessage'),
                                  info.get('LockID'),
                                  info.get('LastLock'))

        if 'BatteryState' in info:
            bs = device.command._parseBatteryStatus(info['BatteryState'])
            device.command._battery = lastContact, bs


    @synchronized
    def getDevices(self,
                   update: bool = False,
                   timeout: Union[int, float] = 10.0,
                   managerTimeout: Optional[int] = None,
                   offline: bool = False,
                   callback: Optional[Callable] = None) -> List["Recorder"]:
        """
            Get a list of remote data recorder objects from the MQTT broker.
            This method also updates the status of existing MQTT `Recorder`
            instances.

            :param update: If `True`, update previously discovered devices
                connected via USB (serial or storage device) to an MQTT
                interface and include them in the results.
            :param timeout: Time (in seconds) to wait for a response from the
                Device Manager before raising a `DeviceTimeout` exception.
                `None` or -1 will wait indefinitely.
            :param managerTimeout: A value (in seconds) that overrides the
                remote Device Manager's timeout that excludes inactive
                devices. 0 will return all devices, regardless of how long it
                has been since they reported to the Device Manager.
            :param offline: If `True`, include devices that are reported to
                have disconnected.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function
                requires no arguments.
        """
        devices = []

        items = self.getDeviceInfo(timeout, managerTimeout, callback)

        for n, listItem in enumerate(items):
            sn = 'missing!'
            try:
                sn = listItem['SerialNumber']
                if sn in self.exclude:
                    continue

                infoIdx = listItem['GetInfoResponse']['InfoIndex']
                info = bytes(listItem['GetInfoResponse']['InfoPayload'])

                if infoIdx != 0:
                    logger.error(f'DeviceListItem {n} (SN {sn}) from Manager '
                                 f'had wrong InfoIndex {infoIdx!r}, continuing')
                    continue

            except KeyError as err:
                logger.error(f'DeviceListItem {n} (SN {sn}) from Manager '
                             f'did not contain {err.args[0]!r}, continuing')
                continue

            with _module_busy:
                device = RECORDERS.get(hash(info), None)
                systemState = listItem.get('DeviceStatusCode')
                if systemState is None:
                    systemState = listItem.get('CommandResponseCode')

                if device is None and not offline and systemState in (100, -110):
                    # Don't instantiate disconnected devices
                    continue

                # if device and not update and not device.isRemote:
                #     continue

                try:
                    if not device or not device.isRemote:
                        devtype = Recorder
                        for dt in RECORDER_TYPES:
                            if dt._isRecorder(info):
                                devtype = dt
                                break
                        device = devtype('remote', devinfo=info)
                        device.command = MQTTCommandInterface(device, self)
                        device._devinfo = MQTTDeviceInfo(device)

                    if not device:
                        logger.error(f'getDevices(): Could not find '
                                     f'Recorder subclass for {n}, continuing')
                        continue

                except (DeviceError, ValueError) as err:
                    logger.error(f'getDevices(): Error instantiating device for {n}: "'
                                 f'{err!r}", continuing.')
                    continue

                self._updateDeviceInfo(device, listItem)

                RECORDERS.pop(hash(info), None)
                RECORDERS[hash(info)] = device
                RECORDERS_BY_SN[device.serialInt] = device

                if not offline and systemState in (100, -110):
                    # Update known offline devices, but don't return them
                    continue

                devices.append(device)

        # Remove old cached devices. Ordered dictionaries assumed!
        if len(RECORDERS) > RECORDER_CACHE_SIZE:
            for k in list(RECORDERS.keys())[-RECORDER_CACHE_SIZE:]:
                del RECORDERS[k]

        return devices


    def findDevice(self,
                   sn: Optional[Union[str, int]] = None,
                   chipId: Optional[Union[str, int]] = None,
                   timeout: Union[int, float] = 10.0,
                   managerTimeout: Optional[int] = None,
                   offline: bool = False,
                   callback: Optional[Callable] = None
                   ) -> Union[Recorder, None]:
        """ Find a specific remote recorder by serial number or unique chip
            ID. One or the other must be provided, but not both. This is
            equivalent to `endaq.device.findDevice()` for remote devices.

            :param sn: The serial number of the recorder to find. Cannot be
                used with `chipId`. It can be an integer or a formatted serial
                number string (e.g., `12345` or `"S00012345"`).
            :param chipId: The chip ID of the recorder to find. Cannot be used
                with `sn`. It can be an integer or a hex string.
            :param timeout: Time (in seconds) to wait for a response from the
                Device Manager before raising a `DeviceTimeout` exception.
                `None` or -1 will wait indefinitely.
            :param managerTimeout: A value (in seconds) that overrides the
                remote Device Manager's timeout that excludes inactive
                devices. 0 will return all devices, regardless of how long it
                has been since they reported to the Device Manager.
            :param offline: If `True`, include devices that are reported to
                have disconnected.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will
                be cancelled. The callback function requires no arguments.
        """
        with _module_busy:
            if sn and chipId:
                raise ValueError('Either a serial number or chip ID is required, not both')
            elif sn is None and chipId is None:
                raise ValueError('Either a serial number or chip ID is required')

            if isinstance(sn, str):
                sn = sn.lstrip(string.ascii_letters + "0")
                if not sn:
                    sn = 0
                sn = int(sn)

            for d in self.getDevices(timeout=timeout, managerTimeout=managerTimeout,
                                     offline=offline, callback=callback):
                if sn is not None and d.serialInt == sn:
                    return d
                elif chipId is not None and d.chipId == chipId:
                    return d

            return None


    def getCachedHeader(self, device: Union[int, Recorder]) -> bytearray:
        """ Retrieve a device's cached IDE header data from the Device
            Manager (if known).

            :param device: The device for which to get the header data.
                Either a `Recorder` instance or a device serial number.
            :returns: The cached IDE header data, as undecoded EBML.
        """
        if isinstance(device, Recorder):
            device = device.serialInt
        try:
            cmd = {'EBMLCommand': {'GetIDEHeader': device}}
            response = self.command._sendCommand(cmd)
            return response['GetIDEHeaderResponse']['IDEHeaderData']
        except CommandError as err:
            if 'Unknown serial number' not in str(err):
                raise
            logger.debug(f'Manager does not have cached header for {device}')
            return None
        except KeyError as err:
            raise DeviceError(f"Manager response did not contain {err.args[0]}")


# ===========================================================================
#
# ===========================================================================

class MQTTSerialPort(SimSerialPort):
    """
    A virtual serial port, communicating over MQTT. Instances are created and
    managed by `MQTTConnector`.
    """

    def __init__(self,
                 manager: MQTTConnector,
                 read: Optional[str] = None,
                 write: Optional[str] = None,
                 timeout: Optional[float] = None,
                 write_timeout: Optional[float] = None,
                 maxsize: int = 1024 * 16,
                 qos: int = 1):
        """
            A virtual serial port, communicating over MQTT. For convenience,
            using `MQTTConnector.newPort()` is recommended over
            explicitly instantiating a `MQTTSerialPort` 'manually.'

            :param manager: The port's supporting `MQTTConnector`.
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


    @synchronized
    def open(self):
        """ Open the virtual port with current settings. """
        if self.readTopic and not self.is_open:
            self.manager.subscribe(self.readTopic, qos=self.qos)
        return super().open()


    @synchronized
    def close(self):
        """ Close the virtual port. """
        if self.readTopic:
            self.manager.unsubscribe(self.readTopic)
        return super().close()


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
                 manager: MQTTConnector,
                 make_crc: bool = True,
                 ignore_crc: bool = False,
                 **kwargs):
        """
            Constructor.

            :param device: The Recorder to which to interface.
            :param manager: The `MQTTConnector` to manage the port.
            :param make_crc: If `True`, generate CRCs for outgoing packets.
            :param ignore_crc: If `True`, ignore the CRC on response packets.

            If additional keyword arguments are provided, they will be used
            when opening the serial port.
        """
        if not device.serial:
            raise ValueError('Device must have a serial number')
        self.manager = manager

        self.streamCallback: Optional[Callable] = None
        self._streamPath: Union[str, Path, None] = None
        self._stream: Optional[BinaryIO] = None
        self._streamStartTime: float = 0
        self._streamedBytes: int = 0
        self._lastStreamChunk: bytes = b''
        self._lastChunkTime: float = 0

        super().__init__(device, make_crc=make_crc, ignore_crc=ignore_crc, **kwargs)
        self._streamTopic = MEASUREMENT_TOPIC.format(sn=f'{self.device.serialInt:08d}')


    @property
    def available(self) -> bool:
        """ Is the command interface available and able to accept commands? """
        try:
            _ts, status, _msg = self.getStatus(timeout=1)
        except TimeoutError:
            return False

        return status not in (DeviceStatusCode.RESET_PENDING,
                              DeviceStatusCode.START_PENDING,
                              DeviceStatusCode.STOP_PENDING,
                              DeviceStatusCode.UPLOADING,
                              DeviceStatusCode.WAKING,
                              DeviceStatusCode.SLEEPING,
                              DeviceStatusCode.OFFLINE)


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
        logger.debug(f'{self.device.serial} Setting info index {infoIdx}')

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


    def _getInfo(self,
                 infoIdx: int,
                 timeout: Union[int, float] = 10,
                 interval: float = .25,
                 lock: bool = False,
                 index: bool = True,
                 callback: Optional[Callable] = None) -> bytes:
        """ Retrieve device system information. For 'local' devices, this
            is retrieved via the filesystem. This method is called indirectly
            by methods in `Recorder`.

            :param infoIdx: The index of the information to retrieve.
            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
                `None` or -1 will wait indefinitely.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will
                be cancelled. The callback function should require no arguments.
            :param lock: If `True`, include the current `hostId` in the
                command, as some `SetInfo` commands require.
            :param index: If `True`, include a ``CommandIdx`` in the command,
                and use it to validate the response (if any).
            :return: The raw info, as unparsed EBML binary data. It is up to
                the caller to know how to process the results (e.g., choose
                the correct schema, etc.).
        """
        # Note: Reading config or user calibration requires a LockID
        # lock = index in (5, 6)
        logger.debug(f'{self.device.serial} Getting info index {infoIdx}')
        return super()._getInfo(infoIdx, timeout, interval, lock, index, callback)


    def getStatus(self,
                  timeout: Union[int, float] = 10,
                  callback: Optional[Callable] = None
                  ) -> Tuple[float, Optional[int], Optional[str]]:
        """ Get the device's status.

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should require no
                arguments.
            :return: The device's current status, as a tuple containing the
                timestamp of the status update, the status code, and the
                corresponding status message (if any).
        """
        # MQTT devices report state changes automatically, not just in
        # response to a command.

        if not self.manager.autoupdate:
            # autoupdate means manager state updates update device.
            # If not autoupdate, update only in response to GetDeviceList.
            self.manager.getDevices(timeout=timeout, managerTimeout=0,
                                    offline=True, callback=callback)

        self._statusChanged.clear()
        return self.status


    def awaitDismount(self,
                      timeout: Optional[Union[int, float]] = None,
                      callback: Optional[Callable] = None) -> bool:
        """ Wait for the device to dismount as a drive, indicating it has
            rebooted, started recording, started firmware application, etc.

            *This method is not applicable to devices connected over MQTT.*

            :return: `False` in all cases.
        """
        # FUTURE: Implement this if the device can report via command if it
        #  is mounted as an MSD.
        return False


    def awaitRemount(self,
                     update: bool = False,
                     paths: Optional[List[Filename]] = None,
                     strict: bool = True,
                     timeout: Optional[Union[int, float]] = None,
                     interval: float = 0.125,
                     callback: Optional[Callable] = None) -> bool:
        """ Wait for the device to reappear as a drive, indicating it has
            been reconnected, completed a recording, finished firmware
            application, etc.

            *This method is not applicable to devices connected over MQTT.*

            :return: `False` in all cases.
        """
        # FUTURE: Implement this if the device can report via command if it
        #  is mounted as an MSD.
        return False


    def getBatteryStatus(self,
                         timeout: Union[int, float] = 1,
                         callback: Optional[Callable] = None) -> Union[dict, None]:
        """ Get the status of the recorder's battery. Not supported on all
            devices.

            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should require no
                arguments.
            :return: A dictionary with the parsed battery status. It will
                always contain the key `"hasBattery"`, and if that is `True`,
                it will contain other keys:

                * `"charging"`: (bool)
                * `"percentage"`: (bool) `True` if the reported charge
                    level is a percentage, or 3 states (0 = empty,
                    255 = full, anything else is 'some' charge).
                * `"level"`: (int) The current battery charge level.

                If the device is capable of reporting if it is receiving
                external power, the dict will contain `"externalPower"`
                (bool).
        """
        if not self.manager.autoupdate:
            return super().getBatteryStatus(timeout, callback)
        return self._battery[1]


    # =======================================================================
    # Lock ID: A weakly-enforced means of claiming exclusive use of a device.
    # =======================================================================

    def getLockID(self,
                  timeout: Union[int, float] = 5,
                  callback: Optional[Callable] = None) -> Union[bytearray, bytes, None]:
        """ Get the device's current lock ID, if any. Not supported by all
            device types or firmware versions.

            Lock IDs are a weakly-enforced means of requesting exclusive use
            of a device. If a device has a lock ID set, commands sent without
            that ID will generate an error.

            :param timeout: Time (in seconds) to wait for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will
                be cancelled. The callback function should require no arguments.
            :returns: The device's current lock ID, if any.
        """
        if not self.manager.autoupdate:
            return super().getLockID(timeout, callback)

        # Device Manager should keep this up to date.
        return self.lockId[1]


    # =======================================================================
    # Wi-Fi - These functions cannot be used over MQTT.
    # =======================================================================

    def setAP(self,
              ssid: str,
              password: Optional[str] = None,
              wait: bool = False,
              timeout: Union[int, float] = 10,
              callback: Optional[Callable] = None):
        """ Quickly set the Wi-Fi access point (router) and password.
            Only applicable to devices connected via USB.

            :raises UnsupportedFeature: This cannot be done via MQTT.
        """
        raise UnsupportedFeature(f'Wi-Fi cannot be configured via MQTT')


    def setWifi(self,
                wifi_data: dict,
                timeout: Union[int, float] = 10,
                interval: float = 1.25,
                callback: Optional[Callable] = None):
        """ Configure all known Wi-Fi access points. Only applicable to
            devices connected via USB.

            :raises UnsupportedFeature: This cannot be done via MQTT.
                """
        raise UnsupportedFeature(f'Wi-Fi cannot be configured via MQTT')


    def queryWifi(self,
                  timeout: Union[int, float] = 10,
                  interval: float = .25,
                  callback: Optional[Callable] = None) -> Union[None, dict]:
        """ Check the current state of the Wi-Fi (if present). Only
            applicable to devices connected via USB.

            :raises UnsupportedFeature: This cannot be done via MQTT.
        """
        raise UnsupportedFeature(f'Wi-Fi cannot be configured via MQTT')


    def scanWifi(self,
                 timeout: Union[int, float] = 10,
                 interval: float = .25,
                 callback: Optional[Callable] = None) -> Union[None, list]:
        """ Initiate a scan for Wi-Fi access points (APs). Applicable only
            to devices with Wi-Fi hardware. Only applicable to devices
            connected via USB.

            :raises UnsupportedFeature: This cannot be done via MQTT.
        """
        raise UnsupportedFeature(f'Wi-Fi cannot be configured via MQTT')


    # =======================================================================
    #
    # =======================================================================

    @property
    def canStream(self) -> bool:
        """ Is the device capable of streaming data?
        """
        # TODO: Check device config to see if the option is enabled?
        return True


    @synchronized
    def startStream(self,
                    path: Union[str, Path],
                    streamCallback: Optional[Callable] = None) -> bool:
        """ Start receiving and writing data streamed from the device. Note
            that this does not send the start command to the device; that
            `startRecording()` must be done explicitly before calling
            `startStream()`.

            :param path: The name of the directory to which to save the
                streamed data. The names of the individual ``.IDE``
                filenames will consist of the device serial number and
                the date/time (e.g., ``SERIALNO_yyyymmdd_HHMMSS.IDE``).
            :param streamCallback: A function to call each time a 'chunk'
                of streamed data arrives. It should take two parameters:
                the `Recorder` instance, and the number of bytes in the
                chunk. Note: Unlike other callback functions, its return
                value is ignored, so returning `False` does not cancel
                the operation.
            :returns: `True` if opening the file and subscribing to the
                stream was successful, `False` if streamed data is already
                being received.
        """
        self.streamCallback = streamCallback or self.streamCallback
        if self.streaming() and path != self._streamPath:
            return False

        self._streamPath = path
        self._createStreamFile()

        self._streamStartTime = 0
        self._streamedBytes = 0
        self._lastStreamChunk = b''

        self.manager._streamers[self._streamTopic] = self
        self.manager.subscribe(self._streamTopic)
        return True


    @synchronized
    def _createStreamFile(self):
        """ Start a new IDE file.
        """
        if self._stream and not self._stream.closed and self._streamedBytes > 0:
            self._stream.close()
        filename = f"{self.device.serial}_{datetime.now().strftime('%y%m%d_%H%M%S')}.IDE"
        self._stream = open(os.path.join(self._streamPath, filename), 'wb')
        logger.debug(f"Saving stream to {self._stream}")


    @synchronized
    def stopStream(self) -> bool:
        """ Stop receiving and writing data streamed from the device. Note
            that this does not send the stop command to the device; that
            must be done explicitly, either before or after calling
            `stopStream()`.

            :returns: `True` if the command was successful, `False` if
                not already receiving/saving streamed data.
        """
        if not self.streaming():
            return False

        self.streamCallback = None
        self.manager._streamers.pop(self._streamTopic, None)
        self.manager.unsubscribe(self._streamTopic)
        self._stream.close()
        return True


    @synchronized
    def streaming(self) -> bool:
        """ Is this instance receiving and recording data streamed from the device?
        """
        return (self._streamTopic in self.manager._streamers
                and self._stream and not self._stream.closed
                # and self.status[1] == DeviceStatusCode.STREAMING
                )


    @synchronized
    def _writeStreamChunk(self, chunk: bytearray) -> int:
        """ Write a chunk of streamed measurement data to file. Called by
            the `MQTTConnector`.

            :param chunk: The payload of a ``measurement`` topic message.
            :returns: The number of bytes written.
        """
        if self._stream is None or self._stream.closed:
            logger.error(f'{self.device.serial} received stream chunk, but file not open!')
            return 0

        if chunk.startswith(EBML_ID_BYTES):
            self._createStreamFile()

        numbytes = self._stream.write(chunk)
        self._streamedBytes += numbytes
        self._lastStreamChunk = chunk
        self._lastChunkTime = time()
        self._streamStartTime = self._streamStartTime or self._lastChunkTime

        if self.streamCallback:
            self.streamCallback(self.device, numbytes)

        return numbytes
