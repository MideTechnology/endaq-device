from collections import defaultdict
from io import BytesIO
import os.path
import sys
from threading import Thread
from time import time
from typing import Any, ByteString, Dict, Optional, Tuple, Union

import ebmlite
from ebmlite.decoding import readElementID, readElementSize
from ..client import dump, synchronized
from ..command_interfaces import CommandError
from ..response_codes import DeviceStatusCode
from .mqtt_interface import MQTT_BROKER, MQTT_PORT, getMyIP, makeClientID

import paho.mqtt.client

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from .mqtt_client import MQTTClient
from .mqtt_interface import STATE_TOPIC, HEADER_TOPIC, MEASUREMENT_TOPIC

# ===========================================================================
#
# ===========================================================================

MIDE_SCHEMA = ebmlite.loadSchema('mide_ide.xml')
CDB_ID = MIDE_SCHEMA['ChannelDataBlock'].id
EBML_ID_BYTES = bytes([0x1A, 0x45, 0xDF, 0xA3])

DEVICE_TIMEOUT = 60 * 5  # seconds


# ===========================================================================
#
# ===========================================================================

class MQTTDevice:
    """
    This class is used by `MQTTDeviceManager` to keep track of a device/process
    presenting itself as an enDAQ recorder over MQTT. It handles capturing and
    caching metadata. Not to be confused with `endaq.device.Recorder`, which
    is a more thorough representation of the device itself, for configuration
    and control purposes; this class is more abstract.
    """

    def __init__(self, 
                 manager: "MQTTDeviceManager",
                 sn: int):
        """ Object for handling streamed IDE data arriving as a series of 
            messages. The messages are not necessarily aligned with the
            EBML elements.

            :param manager: MQTTDeviceManager instance.
            :param sn: The corresponding device serial number.
        """
        logger.debug(f'Created new MQTTDevice (SN: {sn})')
        self.manager = manager
        self.sn = sn

        # Device info, received via `state` topic.
        self.devinfo: ByteString = None

        self.status: tuple[Optional[int], Optional[str]] = None, None
        self.totalMsgs = 0

        # For parsing the `measurement` data to extract IDE header
        self.buffer = BytesIO()
        self.elementSize: int = 0  # Non-zero after the start of an element is received
        self.header = bytearray()
        self.headerBuffer = bytearray()
        self.readingHeader: bool = False
        self.headerTopic = HEADER_TOPIC.format(sn=self.sn)

        self.measurementTopic = MEASUREMENT_TOPIC.format(sn=self.sn)
        self.manager.client.message_callback_add(self.measurementTopic, manager.onMeasurementMessage)
        self.manager.client.subscribe(self.measurementTopic)
        logger.debug(f'Subscribed to {self.measurementTopic}')


    def __del__(self):
        try:
            self.manager.client.unsubscribe(self.measurementTopic)
        except (AttributeError, TypeError, RuntimeError):
            pass


    @synchronized
    def append(self, msg: bytes):
        """ Handle an incoming chunk of IDE data. If the message completes
            an element, it is handled.

            :param msg: A chunk of IDE data, the payload of a message
                received on a 'measurement' topic.
        """
        logger.debug(f'Received {len(msg)} bytes from {self.sn}')
        self.totalMsgs += 1

        if msg.startswith(EBML_ID_BYTES):
            logger.debug(f'Received EBML header from {self.sn}')
            self.readingHeader = True
            self.elementSize = 0
            self.buffer = BytesIO()

        if not self.readingHeader:
            return

        # Append incoming message to the buffer
        end = self.buffer.seek(0, os.SEEK_END) + self.buffer.write(msg)
        self.buffer.seek(0)

        try:
            if not self.elementSize:
                # Not waiting for an element to complete; start reading
                elementId, idlen = readElementID(self.buffer)
                esize, sizelen = readElementSize(self.buffer)
                self.elementSize = esize + idlen + sizelen

                if elementId == CDB_ID:
                    # Received data, assume previous elements were header,
                    # and now it's been read.
                    self.readingHeader = False
                    return

            if end >= self.elementSize:
                # Received at least one element (or enough data for one)
                # Send to `idelib` parser, then clear the parsed data from the buffer
                self.buffer.seek(0)
                data = self.buffer.read(self.elementSize)
                self.header.extend(data)

                # Removed read element from buffer
                # (It is assumed the fp is left just after the element)
                self.buffer = BytesIO(self.buffer.read())
                self.elementSize = 0

        except OSError as err:
            # Raised if buffer too short to contain a complete element ID tag.
            # This will/should change in `ebmlite` in the near future, and
            # this must be revised if the exception type or message change!
            if str(err).startswith(('Invalid length', 'Cannot decode')):
                return
            logger.error("Unexpected IOError handling measurement EBML", exc_info=True)

        except (ValueError, TypeError, IndexError) as err:
            # Shouldn't happen in typical operation
            logger.error(f"{type(err).__name__} handling measurement EBML: {err}", exc_info=True)


    def validateHeader(self, data: bytes) -> bool:
        """ Verify that header data is complete and valid.

            :param data: Encoded EBML data containing the header of an IDE
                file.
        """
        try:
            parsed = ebmlite.loadSchema('mide_ide.xml').loads(data)
            dumped = parsed.dump()

            # Mandatory elements in the header
            for name in ('CalibrationList', 'RecordingProperties', 'TimeBaseUTC'):
                if name not in dumped:
                    logger.error(f'Header from {self.sn} did not contain required {name}')
                    return False

            # Optional elements in header (technically not required, but their
            # absence could mean something else is wrong)
            for name in ('Sync', 'RecorderConfigurationList'):
                if name not in dumped:
                    logger.warning(f'Header from {self.sn} contained no {name}')

            return True

        except (IOError, TypeError, ValueError) as err:
            logger.error(f"{type(err).__name__} validating header: {err}", exc_info=True)
            return False


    @synchronized
    def processHeader(self, data: bytes):
        """ Handle a completed IDE header, either read 'live' from the stream
            or loaded from a cache.

            :param data: Encoded EBML data containing the header of an IDE
                file.
        """
        if not self.validateHeader(data):
            return

        info = self.manager.client.publish(self.headerTopic, data, retain=True)
        if info.rc != paho.mqtt.client.MQTT_ERR_SUCCESS:
            logger.error(f'Error publishing header: {info.rc!r}')
            return
        try:
            info.wait_for_publish(1.0)
        except RuntimeError as err:
            logger.error(f'Error waiting for header to publish: {err!r}')


    def _getCacheFile(self,
                     filename: Optional[str] = None,
                     create: bool = True) -> str:
        """ Get the full path to this device's cached header data.

            :param filename: The base name of the cache file, if not
                ``<sn>_header.ide`` (the default).
            :param create: If `True`, create the directories for the
                cache files. Mainly for use when saving.
            :return: The full path to the cache file.
        """
        filename = filename or f'{self.sn}_header.ide'
        if sys.platform == 'win32':
            root = os.path.expandvars(r'%APPDATA%\endaq')
        else:
            root = os.path.expanduser('~/.endaq')
        dirname = os.path.abspath(os.path.join(root, 'mqtt_manager'))
        if create:
            os.makedirs(dirname, exist_ok=True)
        return os.path.join(dirname, filename)


    def loadHeader(self) -> bytes:
        """ Load cached header data, if available.

            :return: Encoded EBML data containing the header of an IDE
                file, or `None` if no cached header is available.
        """
        try:
            filename = self._getCacheFile(create=False)
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    return f.read()
        except IOError:
            logger.error('Error loading header data', exc_info=True)

        return None


    def saveHeader(self, data: bytes) -> None:
        """ Save header data to a cache file.

            :param data: Encoded EBML data containing the header of an IDE
                file.
        """
        try:
            filename = self._getCacheFile(create=True)
            with open(filename, 'wb') as f:
                f.write(data)
        except IOError:
            logger.error('Error saving header data', exc_info=True)


# ===========================================================================
#
# ===========================================================================

class MQTTDeviceManager(MQTTClient):
    """
    A client that monitors several MQTT topics, providing additional features
    for device discovery and data streaming.
    """

    DEFAULT_DEVINFO = {
        'RecorderTypeUID':  0b11 << 30,
    }


    def __init__(self,
                 client: paho.mqtt.client.Client,
                 make_crc: bool = True,
                 ignore_crc: bool = False):
        """ A client that monitors several MQTT topics, providing additional
            features for device discovery and data streaming.

            :param client: The manager's MQTT client.
            :param make_crc: If `True`, generate CRCs for outgoing commands
                and responses.
            :param ignore_crc: If `False`, do not validate incoming commands
                or responses.
        """
        super().__init__(client, sn="manager", name="MQTT Device Manager",
                         make_crc=make_crc, ignore_crc=ignore_crc)

        self.knownDevices: dict[int, MQTTDevice] = {}

        # Buffers for each topic and serial number
        self.buffers: dict[int, ByteString] = defaultdict(bytearray)
        
        # Last message from each topic. For testing, might remove later.
        self.lastMessages: dict[str, ByteString] = {}
        
        # Last contact times on any topic (serial number, epoch timestamp)
        self.lastContact: dict[int, int] = {}

        self.stateSubTopic = STATE_TOPIC.format(sn='+')
        self.client.message_callback_add(self.stateSubTopic, self.onStateMessage)



    def getSenderSerial(self, topic: str) -> Union[int, str]:
        """ Extract the sending device's serial number from the name of an
            MQTT topic.

            :param topic: The message topic.
            :return: The serial number and the topic's category ("state", 
                "measurement", etc.).
        """
        parts = topic.split('/')  # TODO: regex?
        if len(parts) < 2:
            raise ValueError(f'Could not get SN from topic {topic!r}')
        sn = parts[1]

        try:
            sn = int(sn.lstrip('SWXC0'))
        except (TypeError, ValueError):
            pass

        return sn


    def getDevice(self, sn: int) -> MQTTDevice:
        """ Get or create an `MQTTDevice` instance.

            :param sn: The sending device's serial number.
        """
        try:
            return self.knownDevices[sn]
        except KeyError:
            return self.knownDevices.setdefault(sn, MQTTDevice(self, sn))


    # =======================================================================
    # Message handlers, called by the MQTT message callback (`onMessage()`).
    # =======================================================================


    def onConnect(self, *args):
        """ MQTT event handler called when the client connects.
        """
        super().onConnect(*args)

        self.client.subscribe(self.stateSubTopic)
        logger.debug(f"Subscribed to {self.stateSubTopic}")

        for dev in self.knownDevices.values():
            self.client.subscribe(dev.measurementTopic)
            logger.debug(f'Subscribed to {dev.measurementTopic}')


    def onStateMessage(self, _client, _userdata, message):
        """ Handle a message received in the announcement topic.
        """
        if message.topic == self.stateTopic:
            # Ignore own state message
            logger.debug('ignoring own state update')
            return

        packet = message.payload
        sn = self.getSenderSerial(message.topic)

        try:
            response = self.command._decode(packet)['EBMLResponse']
        except CommandError:
            logger.error(f'onStateMessage: Bad packet from {sn!r} starting with {dump(packet)}')
            return
        except KeyError:
            logger.error(f'onStateMessage: Message from {sn!r} did not contain an EBMLResponse element')
            return

        # TODO: Check RecorderTypeUID to see if this is a recorder? Non-recorder entities
        #  (identified by bit 31 being set) don't need to be tracked the same way.

        device = self.getDevice(sn)
        device.status = response.get('DeviceStatusCode'), response.get('DeviceStatusMessage')

        try:
            getinfo = response['GetInfoResponse']
            index = getinfo.get('InfoIndex', 0)
            if index != 0:
                logger.error(f'onStateMessage: state update from {sn} had wrong InfoIndex ({index})!')
            else:
                device.devinfo = getinfo
        except KeyError as err:
            logger.error(f'onStateMessage: Response from {sn} missing element {err.args[0]!r}!')


    def onMeasurementMessage(self, _client, _userdata, message):
        """ Handle a message received in the measurement topic. This is
            *not* the registered MQTT message callback; that's `onMessage()`,
            which calls this.
        """
        packet = message.payload
        sn = self.getSenderSerial(message.topic)

        if sn not in self.knownDevices:
            logger.info(f'Got measurement from {sn!r} before status!')

        self.getDevice(sn).append(packet)


    # =======================================================================
    # Commands: Methods for each command handled by the `CommandClient`.
    # =======================================================================

    def command_GetDeviceList(
                self,
                payload: Any,
                lockId: Optional[ByteString] = None
            ) -> Tuple[Dict[str, Any], Optional[DeviceStatusCode], Optional[str]]:
        """ Handle a ``GetDeviceList`` command (EBML ID 0x5C00).
        """
        devices = []

        timeout = payload.get('Timeout', DEVICE_TIMEOUT)

        for sn, dev in self.knownDevices.items():
            last = int(self.lastContact.get(sn, time()))
            if timeout and time() - last > timeout:
                logger.debug(f'GetDeviceList: skipping {sn} due to timeout')
                continue

            item = {'SerialNumber': dev.sn,
                    'LastContact': last,
                    'GetInfoResponse': dev.devinfo}

            if dev.status[0] is not None:
                item['DeviceStatusCode'] = dev.status[0]
            if dev.status[1]:
                item['DeviceStatusMessage'] = dev.status[1]

            devices.append(item)

        # Element DeviceListItem marked as 'multiple', so value is a list.
        return {'DeviceList': {'DeviceListItem': devices}}, None, None


# ===========================================================================
# Test code, will be removed.
# ===========================================================================

def run(host: Optional[str] = MQTT_BROKER,
        port: int = MQTT_PORT,
        background: bool = True,
        clientArgs: Dict[str, Any] = None,
        connectArgs: Dict[str, Any] = None):
    host = host or getMyIP()

    clientArgs = clientArgs or {}
    connectArgs = connectArgs or {}
    clientArgs.setdefault('client_id', makeClientID("MQTTDeviceManager"))

    logger.debug(f'Instantiating MQTT client ({clientArgs["client_id"]})')
    client = paho.mqtt.client.Client(paho.mqtt.client.CallbackAPIVersion.VERSION2,
                                     **clientArgs)
    logger.debug(f'Connecting to MQTT Broker on {host}:{port}')
    client.connect(host, port, 60, **connectArgs)

    logger.debug('Instantiating MQTTDeviceManager')
    manager = MQTTDeviceManager(client)

    if background:
        logger.debug('starting loop thread')
        thread = Thread(target=client.loop_forever)
        thread.start()
        return manager
    else:
        logger.debug('entering loop')
        try:
            client.loop_forever()
        except KeyboardInterrupt:
            pass
        logger.debug('exited loop')


if __name__ == "__main__":
    run(background=False)
