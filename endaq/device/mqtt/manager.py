"""
MQTT Device Manager
"""
from collections import defaultdict
# import inspect
from io import BytesIO
import os.path
import struct
import sys
from time import time
from typing import Any, ByteString, Dict, List, Optional, Tuple, Union

import ebmlite
from ebmlite.decoding import readElementID, readElementSize

import paho.mqtt.client

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from ..client import dump, synchronized
from ..response_codes import DeviceStatusCode, CommandResponseCode
from ..command_interfaces import CommandInterface, CommandError, CRCError, DeviceError
from .mqtt_interface import MQTT_BROKER, MQTT_PORT, getMyIP, makeClientID
from .advertising import Advertiser
from .mqtt_discovery import DEFAULT_NAME
from .mqtt_client import MQTTClient
from .mqtt_interface import STATE_TOPIC, HEADER_TOPIC, MEASUREMENT_TOPIC, COMMAND_TOPIC


# ===========================================================================
# 'Constants'
# ===========================================================================

CDB_ID = 0xA1  # EBML ID of IDE ChannelDataBlock element

# Raw bytes of EBML IDs for quickly identifying elements in streams without
# needing to parse the data.
EBML_ID_BYTES = b'\x1A\x45\xDF\xA3'  # To identify `EBML` elements in stream
NEWLOCKID_ID_BYTES = b'\x5A\x02'  # Raw `NewLockID`, to identify `SetLockID` commands

DEVICE_TIMEOUT = 60 * 5  # seconds

# Maximum valid difference between device and system time. Times reported by
# the device that differ from system time by this amount or more are
# considered untrustworthy.
MAX_DRIFT = 60 * 60 * 24 * 2

# Paths for cached data (IDE headers, etc.)
if sys.platform == 'win32':
    CACHE_PATH = os.path.expandvars(r'%APPDATA%\endaq\mqtt_manager')
else:
    CACHE_PATH = os.path.expanduser('~/.endaq/mqtt_manager')


# ===========================================================================
#
# ===========================================================================

class ValidationError(ValueError):
    """ Exception raised if IDE header data fails validation. """


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
        if isinstance(sn, int):
            self.sn = f'{sn:08d}'

        # Timestamps of various things to/from the device.
        self.lastContact: float = 0
        self.lastCommand: float = 0
        self.lastCommandID: int = None
        self.lastMeasurement: float = 0
        self.lastHeader: float = 0
        self.lastLock: float = 0

        # Device info, received via `state` topic, and device's reported time.
        self.stateInfo: Dict[str, Any] = None
        self.infoTime: int = 0

        self.lockId: bytes =  '\x00' * 16
        self.totalMsgs = 0

        # For parsing the `measurement` data to extract IDE header
        self.buffer = BytesIO()
        self.elementSize: int = 0  # Non-zero after the start of an element is received
        self.header = bytearray()
        self.headerBuffer = bytearray()
        self.readingHeader: bool = False
        self.headerTopic = HEADER_TOPIC.format(sn=self.sn)

        header = self.loadHeader()
        if header:
            self.header = bytearray(header)
            self.publishHeader(save=False)

        self.measurementTopic = MEASUREMENT_TOPIC.format(sn=self.sn)
        self.manager.client.message_callback_add(self.measurementTopic,
                                                 self.onMeasurementMessage)
        self.manager.client.subscribe(self.measurementTopic)
        # logger.debug(f'Subscribed to {self.measurementTopic}')

        self.commandTopic = COMMAND_TOPIC.format(sn=self.sn)
        self.manager.client.message_callback_add(self.commandTopic,
                                                 self.onCommandMessage)
        self.manager.client.subscribe(self.commandTopic)
        # logger.debug(f'Subscribed to {self.commandTopic}')


    def __del__(self):
        try:
            self.manager.client.unsubscribe(self.measurementTopic)
            self.manager.client.unsubscribe(self.commandTopic)
        except (AttributeError, TypeError, RuntimeError):
            pass


    # =======================================================================
    # State info management
    # =======================================================================

    @synchronized
    def updateStateInfo(self, info: Dict[str, Any]):
        """ Update the information with data published by the actual device
            to its `state` topic. Called by the Manager.
        """
        now = time()
        self.stateInfo = info

        try:
            # Get device's time, which could be wrong (power loss, etc.)
            t = CommandInterface._TIME_PARSER.unpack_from(info['ClockTime'])[0]
            if abs(now - t) < MAX_DRIFT:
                self.infoTime = t
            else:
                logger.warning(f'state update from {self.sn} ClockTime '
                               f'differs from system by {now - t}')
        except KeyError:
            pass
        except (struct.error, IndexError):
            logger.error(f'state update from {self.sn} ClockTime '
                         f'had bad value: {info["ClockTime"]!r}!')

        if not self.lastContact:
            # First state update, probably a retained message
            self.lastContact = self.infoTime or now
        else:
            self.lastContact = now

        lockId = info.get('LockID', self.lockId)
        if lockId != self.lockId:
            self.lastLock = self.lastContact
        self.lockId = lockId

        self.stateInfo['SerialNumber'] = int(self.sn)


    @synchronized
    def getStateInfo(self) -> Dict[str, Any]:
        """ Get the device's state info.
        """
        item = {'LastContact': int(max(self.lastContact, self.infoTime)),
                'LastMeasurement': int(self.lastMeasurement),
                'LastHeader': int(self.lastHeader),
                'LastCommand': int(self.lastCommand),
                'LastLock': int(self.lastLock),
                'LockID': self.lockId}

        if self.lastCommandID:
            item['LastCommandID'] = self.lastCommandID

        self.stateInfo.update(item)
        return self.stateInfo


    # =======================================================================
    # LockID management
    # =======================================================================

    @synchronized
    def onCommandMessage(self, _client, _userdata, message):
        """ Handle a command message to the device, scraping any change to
            the `LockID`.
        """
        self.lastCommand = time()
        msg = message.payload

        try:
            schema = ebmlite.loadSchema('command-response.xml')
            command = (self.manager.command
                       ._decodeCommand(msg)['EBMLCommand'])
            for cmd in command:
                if cmd not in ('CommandIdx', 'LockID'):
                    self.lastCommandID = schema.elementsByName[cmd].id
                    logger.debug(f'Command to {self.sn}: {cmd!r} ({hex(self.lastCommandID)})')
                    break

            if NEWLOCKID_ID_BYTES in msg:
                setLock = command['SetLockID']
                myId = self.lockId
                oldId = setLock['CurrentLockID']
                newId = setLock['NewLockID']

                if not any(self.lockId) or self.lockId == oldId:
                    self.lockId = newId
                    self.lastLock = self.lastCommand

                if myId != newId:
                    logger.debug(f'Captured SetLockID command for {self.sn}: '
                                 f'{dump(newId, 0)!r}')

        except KeyError as err:
            logger.debug(repr(err))
            pass


    # =======================================================================
    # IDE Header data scraping and management
    # =======================================================================

    @synchronized
    def onMeasurementMessage(self, _client, _userdata, message):
        """ Handle an incoming chunk of IDE data. If the message completes
            an element, it is handled.
        """
        self.totalMsgs += 1
        self.lastMeasurement = self.lastContact = time()
        if self.stateInfo:
            # Device doesn't post state updates while streaming, set
            # device status explicitly.
            self.stateInfo['DeviceStatusCode'] = DeviceStatusCode.STREAMING
            self.stateInfo['CommandResponseCode'] = DeviceStatusCode.STREAMING

        msg = message.payload

        if msg.startswith(EBML_ID_BYTES):
            logger.debug(f'Received start of header from {self.sn}')
            self.readingHeader = True
            self.elementSize = 0
            self.buffer = BytesIO()
            self.header.clear()

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
                    logger.debug(f'Completed reading header from {self.sn}')
                    self.readingHeader = False
                    self.publishHeader()
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
            logger.error("Unexpected IOError handling measurement EBML",
                         exc_info=True)

        except (ValueError, TypeError, IndexError) as err:
            # Shouldn't happen in typical operation
            logger.error(f"{type(err).__name__} handling measurement EBML: {err}",
                         exc_info=True)


    def validateHeader(self, data: bytes) -> Union[bool, Dict[str, Any]]:
        """ Verify that header data is complete and valid. Raises a
            `ValidationError` if validation fails.

            :param data: Encoded EBML data containing the header of an IDE
                file.
            :return: The header data in dictionary form if validation was
                successful.
        """
        try:
            parsed = ebmlite.loadSchema('mide_ide.xml').loads(data)
            dumped = parsed.dump()

            # Mandatory elements in the header
            for name in ('CalibrationList', 'RecordingProperties', 'TimeBaseUTC'):
                if name not in dumped:
                    logger.error(f'Header from {self.sn} did not contain '
                                 f'required element {name!r}')
                    raise ValidationError

            # Optional elements in header (technically not required, but their
            # absence could mean something else is wrong)
            # for name in ('Sync', 'RecorderConfiguration'):
            for name in ('RecorderConfiguration',):
                if name not in dumped:
                    logger.warning(f'Header from {self.sn} contained no {name}'
                                   ' (non-fatal)')

            return dumped

        except (IOError, TypeError, ValueError) as err:
            logger.error(f"{type(err).__name__} validating header: {err}",
                         exc_info=True)
            raise ValidationError


    @synchronized
    def publishHeader(self, save=True):
        """ Handle a completed IDE header, either read 'live' from the stream
            or loaded from a cache.

            :param save: If `True`, write the header to a cache.
        """
        try:
            validated = self.validateHeader(self.header)
        except ValidationError:
            return

        self.lastHeader = validated['TimeBaseUTC'][0]

        if save:
            self.saveHeader(self.header)

        info = self.manager.client.publish(self.headerTopic, self.header,
                                           retain=True)
        if info.rc != paho.mqtt.client.MQTT_ERR_SUCCESS:
            logger.error(f'Error publishing header to {self.headerTopic}: '
                         f'{info.rc!r}')
            return
        try:
            info.wait_for_publish(1.0)
            logger.debug(f'Published IDE header to {self.headerTopic}')
            self.lastHeader = time()
        except RuntimeError as err:
            logger.error(f'Error waiting for header to publish '
                         f'to {self.headerTopic}: {err!r}')


    def _getCacheFile(self,
                     create: bool = True) -> str:
        """ Get the full path to this device's cached header data. The file
            may or may not exist.

            :param create: If `True`, create the directories for the
                cache files. Mainly for use when saving.
            :return: The full path to the cache file.
        """
        if create:
            os.makedirs(CACHE_PATH, exist_ok=True)
        return os.path.join(CACHE_PATH, f'{self.sn}_header.ide')


    def loadHeader(self) -> bytes:
        """ Load cached header data, if available.

            :return: Encoded EBML data containing the header of an IDE
                file, or `None` if no cached header is available.
        """
        try:
            filename = self._getCacheFile(create=False)
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    header = f.read()
                logger.debug(f'Loaded cached header for {self.sn} ({len(header)} bytes)')
                return header
        except IOError:
            logger.error('Error loading header data', exc_info=True)

        return None


    def saveHeader(self, data: bytes) -> None:
        """ Save header data to a cache file.

            :param data: Encoded EBML data containing the header of an IDE
                file.
        """
        logger.debug(f'Saving header data for {self.sn} ({len(data)} bytes)')
        try:
            filename = self._getCacheFile(create=True)
            with open(filename, 'wb') as f:
                f.write(data)
        except IOError:
            logger.error('Error saving header data', exc_info=True)


    @synchronized
    def getHeader(self):
        """ Get the device's IDE header data.
        """
        if not self.header:
            raise CommandError(DeviceStatusCode.ERR_BAD_PAYLOAD,
                               f'No cached header available for {self.sn}')
        if self.readingHeader:
            raise CommandError(DeviceStatusCode.ERR_INTERNAL_ERROR,
                               f'Header data for {self.sn} incomplete, try later')

        return self.header


# ===========================================================================
#
# ===========================================================================

class MQTTDeviceManager(MQTTClient):
    """
    A client that monitors several MQTT topics, keeping track of sensors and
    other devices, and providing additional features for device discovery and
    data streaming.
    """

    DEFAULT_DEVINFO = {
        'RecorderTypeUID':  0b11 << 30,
    }


    def __init__(self,
                 client: paho.mqtt.client.Client,
                 make_crc: bool = True,
                 ignore_crc: bool = False,
                 interval: int = 45):
        """ A client that monitors several MQTT topics, providing additional
            features for device discovery and data streaming.

            :param client: The manager's MQTT client.
            :param make_crc: If `True`, generate CRCs for outgoing commands
                and responses.
            :param ignore_crc: If `False`, do not validate incoming commands
                or responses.
            :param interval: The time between published `state` updates. If
                0, no `state` updates will be published.
        """
        super().__init__(client, "manager", name="MQTT Device Manager",
                         make_crc=make_crc, ignore_crc=ignore_crc,
                         interval=interval)

        self.knownDevices: dict[int, MQTTDevice] = {}

        # Buffers for each topic and serial number
        self.buffers: dict[int, ByteString] = defaultdict(bytearray)
        
        # Last message from each topic. For testing, might remove later.
        self.lastMessages: dict[str, ByteString] = {}
        
        self.stateSubTopic = STATE_TOPIC.format(sn='+')
        self.client.message_callback_add(self.stateSubTopic, self.onStateMessage)


    def getSenderSerial(self, topic: str) -> Union[int, str]:
        """ Extract the sending device's serial number from the name of an
            MQTT topic.

            :param topic: The message topic.
            :return: The serial number. Typically an integer, but special
                cases (like the manager) may have a string value.
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


    @synchronized
    def updateState(self):
        """ Publish an updated set of data to the 'state' topic.
        """
        # curframe = inspect.currentframe()
        # calframe = inspect.getouterframes(curframe, 2)
        # caller = calframe[2][3]
        # logger.debug(f'Updating state topic {self.stateTopic} ({caller})')

        # Schedule the next automatic update
        self.nextUpdate = time() + self.interval

        if not self.client or not self.client.is_connected():
            return

        state, _statusCode, _statusMsg = self.command_GetInfo(0)
        state.update(self.command_GetClock(None)[0])

        # Above is the same as `MQTTClient`. Below adds a subset of the
        # `GetDeviceList` data; device DEVINFO is excluded.
        devices = []

        for dev in self.knownDevices.values():
            item = dev.getStateInfo().copy()
            item.pop('GetInfoResponse', None)
            devices.append(item)

        state['DeviceList'] = {'DeviceListItem': devices}
        # logger.debug('Manager sending state update')

        # Same as `MQTTClient`.
        packet = self.encodeResponse(state)
        self.sendResponse(None, packet, self.stateTopic)


    def cleanCache(self,
                   root: Optional[str] = CACHE_PATH,
                   retention: int = 24) -> Tuple[List[str], List[Exception]]:
        """ Clean out cached header data.

            :param root: The cache file directory, overriding the default.
            :param retention: The cached file retention period. Files not
                modified in `retention` hours will be removed.
        """
        logger.debug(f'MQTTDeviceManager.cleanCache: Clearing cached headers '
                     f'older than {retention} hours from "{root}"...')
        limit = retention * 60 * 60
        errs = []
        cleared = []
        if os.path.isdir(root):
            for f in os.listdir(root):
                if f.lower().endswith('_header.ide'):
                    try:
                        filename = os.path.join(root, f)
                        if time() - os.path.getmtime(filename) > limit:
                            os.remove(filename)
                            cleared.append(filename)
                    except (IOError, OSError) as err:
                        errs.append(err)

        logger.debug(f'MQTTDeviceManager.cleanCache: {len(cleared)} files deleted, '
                     f'{len(errs)} failed.')
        if errs:
            logger.error(f'MQTTDeviceManager.cleanCache failed to remove '
                         f'some cached files: {errs!r}')

        return cleared, errs


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
            # logger.debug('ignoring own state update')
            return

        # logger.debug(f'Received state update from {message.topic}')

        packet = message.payload
        sn = self.getSenderSerial(message.topic)

        try:
            response = self.command._decode(packet)['EBMLResponse']
        except CRCError:
            logger.error(f'onStateMessage: Bad packet CRC from {sn!r} starting with {dump(packet)}')
            return
        except DeviceError as err:
            logger.error(f'onStateMessage: Error handling packet from {sn!r}: {err!r}')
            return
        except KeyError:
            logger.error(f'onStateMessage: Message from {sn!r} did not contain an EBMLResponse element')
            return

        device = self.getDevice(sn)
        device.updateStateInfo(response)
        self.updateState()


    # =======================================================================
    # Commands: Methods for each command handled by the `CommandClient`.
    # =======================================================================

    # noinspection PyUnusedLocal
    def command_GetDeviceList(
                self,
                payload: Any,
                lockId: Optional[ByteString] = None
            ) -> Tuple[Dict[str, Any], Optional[DeviceStatusCode], Optional[str]]:
        """ Handle a ``GetDeviceList`` command (EBML ID 0x5C00).
        """
        devices = []

        timeout = payload.get('Timeout', DEVICE_TIMEOUT)

        for dev in self.knownDevices.values():
            item = dev.getStateInfo()

            if timeout and time() - item['LastContact'] > timeout:
                logger.debug(f'GetDeviceList: skipping {dev.sn} due to timeout ({time() - item["LastContact"]})')
                continue

            devices.append(item)

        # Element DeviceListItem marked as 'multiple', so value is a list.
        return {'DeviceList': {'DeviceListItem': devices}}, None, None


    # noinspection PyUnusedLocal
    def command_GetIDEHeader(
                self,
                payload: Any,
                lockId: Optional[ByteString] = None
            ) -> Tuple[Dict[str, Any], Optional[DeviceStatusCode], Optional[str]]:
        """ Handle a ``GetIDEHeader`` command (EBML ID 0x5C20).
        """
        sn = payload

        if sn is None:
            return {}, DeviceStatusCode.ERR_INVALID_COMMAND, "GetIDEHeader missing SerialNumber"

        dev = self.knownDevices.get(sn)
        if dev is None:
            return {}, DeviceStatusCode.ERR_INVALID_COMMAND, f"Unknown serial number: {sn}"

        try:
            header = dev.getHeader()
        except CommandError as err:
            if err.errno not in (CommandResponseCode.ERR_UNKNOWN_DEVICE,
                                 CommandResponseCode.ERR_BAD_PAYLOAD):
                logger.error(f'Error in GetIDEHeader: {err!r}',
                             exc_info='header' not in str(err).lower())
            return {}, err.errno, str(err)

        response = {'GetIDEHeaderResponse': {'SerialNumber': sn,
                                             'IDEHeaderData': header}}

        return response, None, None


# ===========================================================================
# Test code, will be removed.
# ===========================================================================

def run(host: Optional[str] = MQTT_BROKER,
        port: int = MQTT_PORT,
        advertise: bool = True,
        brokerName: Optional[str] = DEFAULT_NAME,
        background: bool = False,
        clientArgs: Dict[str, Any] = None,
        connectArgs: Dict[str, Any] = None,
        advertArgs: Dict[str, Any] = None,
        managerArgs: Dict[str, Any] = None,
        clean: Optional[int] = None):
    """
    Start the Device Manager and (optionally) the mDNS advertiser.
    This is a temporary implementation and will be refactored.

    :param host: The hostname/IP of the MQTT broker. Defaults to the current
        machine's.
    :param port: The port to which to connect.
    :param advertise: If `True`, start the mDNS advertising of the broker.
    :param brokerName: The name under which the MQTT broker will be advertised.
    :param background: *For testing.* If `True`, this function returns an
        `MQTTDeviceManager` instance with the client loop running in a
        thread. If `False`, the function will run the client loop in the
        foreground and will not return.
    :param clientArgs: A dictionary of additional keyword arguments to be
        used in the instantiation of the `paho.mqtt.client.Client`.
    :param connectArgs: A dictionary of additional keyword arguments to be
        used with `paho.mqtt.client.Client.connect()`.
    :param advertArgs: A dictionary of additional keyword arguments to be
        used in the instantiation of the `Advertiser` (if `advertise` is
        `True`).
    :param managerArgs: A dictionary of additional keyword arguments to be
        used in the instantiation of the `MQTTDeviceManager`.
    :param clean: If not `None`, remove cached header data older than
        `clean` hours on Device Manager startup.
    :return: The running `MQTTDeviceManager` if `background`, else the
        function runs indefinitely without returning.
    """
    clientArgs = clientArgs.copy() if clientArgs else {}
    connectArgs = connectArgs.copy() if connectArgs else {}
    managerArgs = managerArgs.copy() if managerArgs else {}

    host = connectArgs.pop('host', host) or getMyIP()
    port = connectArgs.pop('port', port) or MQTT_PORT
    clientArgs.setdefault('client_id', makeClientID("MQTTDeviceManager"))

    logger.info(f'Instantiating MQTT client ({clientArgs["client_id"]}) '
                f'for broker on {host}:{port}')
    client = paho.mqtt.client.Client(paho.mqtt.client.CallbackAPIVersion.VERSION2,
                                     **clientArgs)
    client.connect(host, port, 60, **connectArgs)

    # logger.info('Instantiating MQTTDeviceManager')
    manager = MQTTDeviceManager(client, **managerArgs)

    if clean is not None:
        manager.cleanCache(retention=clean)

    if advertise:
        kwargs = {'address': host, 'port': port, 'name': brokerName}
        if advertArgs:
            kwargs.update(advertArgs)
        manager.advertiser = Advertiser(**kwargs)
        logger.info(f'Starting advertising broker on {host}:{port} '
                     f'as "{manager.advertiser.fullName}"')
        manager.advertiser.start()

    logger.info("Starting manager's MQTT client loop thread")

    # Test code: this conditional block to be removed (probably)
    if background:
        client.loop_start()
        return manager

    try:
        client.loop_forever()
    except KeyboardInterrupt as err:
        logger.debug(f'{err!r}')
    finally:
        if advertise:
            logger.debug('stopping advertiser')
            manager.advertiser.stop()

    logger.debug('exited loop')

    return manager


# ===========================================================================
#
# ===========================================================================

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('-a', '--address', type=str, default=None,
                        help="MQTT Broker address/hostname. Defaults to this machine.")
    parser.add_argument('-p', '--port', type=int, default=MQTT_PORT,
                        help="MQTT Broker port.")
    parser.add_argument('-s', '--silent', action='store_true',
                        help="Do not advertise the MQTT broker via mDNS.")
    parser.add_argument('-n', '--name', type=str, default=DEFAULT_NAME,
                        help="The advertised name of the MQTT broker.")
    parser.add_argument('-c', '--config', type=str, default=None, metavar="FILENAME",
                        help="The name of a configuration JSON file with additional "
                             "arguments for the Device Manager and advertising. "
                             "Values in the config file will override other "
                             "arguments.")
    parser.add_argument('--clean', type=int, default=None,
                        help="On startup, clean out cached header data older "
                             "than this many hours.")
    args = parser.parse_args()
    kwargs = {'host': args.address, 'port': args.port,
              'advertise': not args.silent, 'brokerName': args.name,
              'clean': args.clean}

    if args.config:
        with open(args.config, 'r') as f:
            config = json.load(f)
            kwargs.update(config)

    run(**kwargs)
