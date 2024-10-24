"""
Base class for software clients that respond like, or work with,
enDAQ hardware.
"""

from threading import Event, Thread
from time import sleep, time
from typing import Any, ByteString, Optional, Tuple, Union

import ebmlite
from ..client import CommandClient, synchronized
from ..hdlc import HDLC_BREAK_CHAR
from ..response_codes import DeviceStatusCode
from .mqtt_interface import COMMAND_TOPIC, RESPONSE_TOPIC, STATE_TOPIC

import paho.mqtt.client

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# ===========================================================================
#
# ===========================================================================

class MQTTClient(CommandClient):
    """
    Base class for software clients that respond like, or work with,
    enDAQ hardware.
    """

    # Non-enDAQ devices identify themselves in their DEVINFO via
    #  `RecorderTypeUID` with bit 31 set. Bits 30-0 can be used for more
    #  specific/descriptive identification of client type.
    DEFAULT_DEVINFO = {
        'RecorderTypeUID': 1 << 31,
    }


    def __init__(self,
                 client: paho.mqtt.client.Client,
                 sn: Union[int, str],
                 make_crc: bool = True,
                 ignore_crc: bool = False,
                 name: str = None,
                 interval: int = 120):
        """ Base class for software clients that respond like, or work with,
            enDAQ hardware.

            :param client: The manager's MQTT client.
            :param sn: The client's serial number. For recorder-like clients
                that interact with the MQTT Device Manager, this should be an
                integer.
            :param make_crc: If `True`, generate CRCs for outgoing commands
                and responses.
            :param ignore_crc: If `False`, do not validate incoming commands
                or responses.
            :param name: The client's name (if applicable). Equivalent to
                the name assigned to device during configuration.
            :param interval: The time between published `state` updates. If
                0, no `state` updates will be published.
        """
        self.client = client
        self.sn = sn
        self.name = name
        self.interval = interval
        self._devinfo = None

        self.commandTopic = COMMAND_TOPIC.format(sn=self.sn)
        self.responseTopic = RESPONSE_TOPIC.format(sn=self.sn)
        self.stateTopic = STATE_TOPIC.format(sn=self.sn)
        self.commandBuffer = bytearray()

        self.stopStateUpdates = Event()
        self.updateThread = None

        super().__init__(make_crc=make_crc, ignore_crc=ignore_crc)

        self.client.on_message = self.onMessage
        self.client.message_callback_add(self.commandTopic, self.onCommandMessage)

        self.client.on_connect = self.onConnect
        self.client.on_disconnect = self.onDisconnect


    def _stateUpdataLoop(self):
        """ The state-updating loop.
        """
        logger.debug(f'Starting state update thread: {self.updateThread}')
        deadline = time() + self.interval
        while not self.stopStateUpdates.is_set():
            if time() < deadline:
                sleep(1)
                continue
            self.updateState()
            deadline = time() + self.interval
        logger.debug(f'Exiting state update thread: {self.updateThread}')


    def startUpdateLoop(self):
        """ Attempt to start the state-updating loop.
        """
        self.killUpdateLoop()
        self.stopStateUpdates.clear()
        self.updateThread = Thread(target=self._stateUpdataLoop, daemon=True)
        self.updateThread.name = f'{type(self).__name__}{self.updateThread.name}'
        self.updateThread.start()


    def killUpdateLoop(self, timeout: float = 5.0) -> bool:
        """ Attempt to shut down the state updating loop.
        """
        self.stopStateUpdates.set()
        if self.updateThread is None:
            return True

        deadline = time() + timeout
        while time() > deadline:
            if self.updateThread and not self.updateThread.is_alive():
                return True
            sleep(0.1)
        logger.error(f'Could not shut down state updating loop {self.updateThread}')
        return False


    def onConnect(self, client, userdata, disconnect_flags, reason_code, properties):
        """ MQTT event handler called when the client connects.
        """
        logger.info(f'Connected to MQTT broker {client.host}:{client.port} '
                    f'({reason_code.getName()})')

        self.client.subscribe(self.commandTopic)
        logger.debug(f'Subscribed to {self.commandTopic}')

        self.updateState()

        if self.interval:
            self.startUpdateLoop()


    def onDisconnect(self, client, _userdata, _disconnect_flags, reason_code, _properties):
        """ MQTT event handler called when the client disconnects.
        """
        self.killUpdateLoop()
        logger.info(f'Disconnected from MQTT broker {client.host}:{client.port} '
                    f'({reason_code.getName()})')


    def __del__(self):
        try:
            self.stopStateUpdates.set()
        except (AttributeError, TypeError, RuntimeError):
            pass
        try:
            self.client.unsubscribe(self.commandTopic)
        except (AttributeError, TypeError, RuntimeError):
            pass


    def iterChunks(self, buf: bytearray, newdata: ByteString = b'') -> ByteString:
        """ Iterate HDLC-escaped chunks of data from a buffer. Ends when
            the buffer no longer contains the HDLC escape character.

            :param buf: The buffer `bytearray`. Note that it will be modified
                in place; chunks are removed as they are yielded.
            :param newdata: Additional data to append to the buffer before
                starting iteration. A convenience.
        """
        if newdata:
            buf.extend(newdata)

        while HDLC_BREAK_CHAR in buf:
            idx = buf.index(HDLC_BREAK_CHAR)
            if idx == 0:
                del buf[0]
                continue

            # Include the HDLC break character
            packet = buf[:idx + 1]
            del buf[:idx + 1]

            yield packet


    def onMessage(self, _client, _userdata, message):
        """ General message handler for any topics not explicitly configured
            with a callback.
        """
        logger.warning(f'Received unexpected message topic: {message.topic}')


    @synchronized
    def onCommandMessage(self, _client, _userdata, message):
        """ Handle a message sent to the client's 'command' topic.
        """
        # Commands with large payloads could potentially be split across
        # messages. This also handles more than one `EBMLCommand` in a
        # message - unlikely, but not impossible.
        for command in self.iterChunks(self.commandBuffer, message.payload):
            self.processCommand(command)


    @synchronized
    def sendResponse(self,
                     recipient: Any,
                     packet: ByteString,
                     topic: str = None):
        """ Transmit a complete, encoded command response packet
            (or 'state' update).
        """
        # Called by methods in `CommandClient` that do all the real work
        topic = topic or self.responseTopic
        info = self.client.publish(topic, bytes(packet))
        if info.rc != paho.mqtt.client.MQTT_ERR_SUCCESS:
            logger.error(f'Error publishing to {topic}: {info.rc!r}')
            return
        try:
            info.wait_for_publish(1.0)
        except RuntimeError as err:
            logger.error(f'Error waiting for response to publishing to {topic}: {err!r}')


    @synchronized
    def updateState(self):
        """ Publish an updated set of data to the 'state' topic.
        """
        state, _statusCode, _statusMsg = self.command_GetInfo(0)
        state.update(self.command_GetClock(None)[0])

        packet = self.encodeResponse({'EBMLResponse': state})
        self.sendResponse(None, packet, self.stateTopic)
        # logger.debug(f'Updated state topic {self.stateTopic}')


    def command_GetInfo_0(self,
                          payload: ByteString,
                          lockId: Optional[int] = None
            ) -> Tuple[ByteString, Optional[DeviceStatusCode], Optional[str]]:
        """ Retrieve the client's DEVINFO. Also used to generate the main
            payload of 'state' topic updates.
        """
        if self._devinfo is None:
            devinfo = self.DEFAULT_DEVINFO.copy()

            if isinstance(self.sn, int):
                devinfo['RecorderSerial'] = self.sn
            if self.name:
                devinfo['UserDeviceName'] = self.name

            devinfo.setdefault('ProductName', type(self).__name__)
            devinfo.setdefault('PartNumber', type(self).__name__)

            schema = ebmlite.loadSchema('mide_ide.xml')
            self._devinfo = schema['RecorderInfo'].encode(devinfo)

        return self._devinfo, None, None
