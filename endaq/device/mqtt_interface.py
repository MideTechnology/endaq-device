"""
VERY EXPERIMENTAL command interface via MQTT. It is only a proof of concept.

The MQTTCommandInterface attemps to send commands via a 'command' channel and
receive responses on a 'response' channel. It works, but is somewhat slow.

Two possible ways to use this:

To set up a regular, USB-attached device with a `SerialCommandInterface`:
    >>> from endaq.device import mqtt_interface
    >>> tester, device = mqtt_interface.setup()
    >>> device.command.ping(b'test')
    2024-01-23 21:08:36,317 DEBUG: TESTER got 19 from mqtt: b'\x80&\x00\n\x80\x8aW\x00\x84test\x88\x81\x01 j~'
    2024-01-23 21:08:37,431 DEBUG: TESTER read 28 of 0 bytes from serial port
    2024-01-23 21:08:37,543 DEBUG: MQTTCommandInterface received 28 bytes: b'\x81\x00\x00\x86@\x13P\x00\x81\x01Q\x00\x81\x01X\x01\x81\x00W\x01\x84test\x82\xc4~'
    Out[5]: bytearray(b'test')

To set up a real wireless device,
    >>> from endaq.device import Recorder, mqtt_interface
    >>> device = Recorder(None)
    >>> command = mqtt_interface.MQTTCommandInterface(device)
    >>> command.startMqtt('localhost', 1883, command="endaq/command", response="endaq/response")
    2024-01-23 21:08:37,543 DEBUG: MQTTCommandInterface received 28 bytes: b'\x81\x00\x00\x86@\x13P\x00\x81\x01Q\x00\x81\x01X\x01\x81\x00W\x01\x84test\x82\xc4~'
    Out[5]: bytearray(b'test')

"""

from copy import deepcopy
import logging
from threading import Thread, Event
from time import sleep, time
from typing import ByteString, Optional, Union, Callable, TYPE_CHECKING

from .command_interfaces import logger, SerialCommandInterface
from .exceptions import *
from .hdlc import HDLC_BREAK_CHAR
from .response_codes import *

if TYPE_CHECKING:
    from .base import Recorder

import paho.mqtt.client as mqtt


# Temporary. For testing.
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
KEEP_ALIVE_INTERVAL = 60*60

# Temporary. Will probably be something uniquely identifiable, e.g.
# a name that includes a device serial number.
MQTT_COMMAND_TOPIC = "endaq/command"
MQTT_RESPONSE_TOPIC = "endaq/response"

logger.setLevel(logging.DEBUG)


# ===========================================================================
#
# ===========================================================================

class MQTTCommandInterface(SerialCommandInterface):
    """
    MQTT Command Interface (proof of concept). Work in progress!

    """
    # TODO: Detach `SerialCommandInterface` from encoding, so subclasses like this don't have
    #  to reimplement as much (e.g., the common parts of `_sendCommand()` and `_readResponse()`),
    #  and are free of irrelevant serial-related detritus.


    def __init__(self,
                 device: 'Recorder',
                 make_crc: bool = True,
                 ignore_crc: bool = False,
                 **kwargs):
        """
        Constructor.

        :param device: The Recorder to which to interface.
        :param make_crc: If `True`, generate CRCs for outgoing packets.
        :param ignore_crc: If `True`, ignore the CRC on response packets.
        :param commandTopic: The name of the MQTT topic to use for enDAQ
            commands.
        :param
        """
        super().__init__(device, make_crc=make_crc, ignore_crc=ignore_crc)
        self._responseBuffer = bytearray()

        self.client = None
        self.commandTopic = None
        self.responseTopic = None
        self.broker = None
        self._thread = None
        self._stopThread = Event()


    # =======================================================================
    # =======================================================================

    def _mqttThreadFunction(self):
        """ MQTT-checking loop, to be called by a separate thread. Can be
            stopped via `_stopThread.set()`.
        """
        while not self._stopThread.is_set():
            self.client.loop(timeout=1.0)
            sleep(0.1)


    def _onMqttConnect(self, client, userdata, flags, rc):
        """ Callback to handle the establishment of a MQTT connection.
        """
        if rc == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f"Connected to broker {self.broker[0]}:{self.broker[1]}")
            client.subscribe(self.responseTopic)
        else:
            logger.error(f"Connection failed with code: {rc}")


    def _onMqttMessage(self, client, userdata, message):
        """ Callback to handle incoming MQTT messages.
        """
        logger.debug(f'MQTTCommandInterface received {len(message.payload)} bytes: {message.payload!r}')
        if message.topic != self.responseTopic:
            logger.warning(f"Got message on topic {message.topic} (shouldn't happen)")
            return

        with self.device._busy:

            self._responseBuffer.extend(message.payload)


    def _onMqttDisconnect(self, client, userdata, rc):
        """ Callback to handle disconnecting from the MQTT broker.
        """
        if rc != 0:
            logger.error("Unexpected disconnection. Trying to reconnect...")
            client.reconnect()


    def startMqtt(self,
                  host: str = MQTT_BROKER,
                  port: int = MQTT_PORT,
                  keepalive: int = KEEP_ALIVE_INTERVAL,
                  command: str = MQTT_COMMAND_TOPIC,
                  response: str = MQTT_RESPONSE_TOPIC):
        """ Start the MQTT client.

            This will eventually be fully integrated and not a separate
            method call.

            :param host: The MQTT broker hostname/address.
            :param port: The MQTT broker port.
            :param keepalive: The maximum period in seconds allowed between
                communications with the broker.
            :param command: The enDAQ command interface topic name.
            :param response: The enDAQ response topic name.
        """
        self.broker = (host, port)
        self.commandTopic = command or self.commandTopic
        self.responseTopic = response or self.responseTopic
        self.client = mqtt.Client()

        self.client.connect(host, port, keepalive)
        self.client.on_connect = self._onMqttConnect
        self.client.on_message = self._onMqttMessage
        self.client.on_disconnect = self._onMqttDisconnect

        self._thread = Thread(name="MQTTControlInterfaceThread",
                              target=self._mqttThreadFunction,
                              daemon=True)
        self._thread.start()


    # =======================================================================
    # =======================================================================

    @classmethod
    def hasInterface(cls, device: "Recorder") -> bool:
        """ Determine if a device supports this `CommandInterface` type.

            :param device: The recorder to check.
            :return: `True` if the device supports the interface.
        """
        if device.isVirtual:
            return False

        # TODO: Some way to identify a device has an MQTT interface.
        #  For now, this CommandInterface is always going to be explicitly created.
        return False


    @classmethod
    def findSerialPort(cls, device: "Recorder"):
        """ Not applicable to `MQTTCommandInterface`. """
        raise NotImplementedError


    def getSerialPort(self, **kwargs):
        """ Not applicable to `MQTTCommandInterface`. """
        raise NotImplementedError


    @property
    def available(self) -> bool:
        """ Is the command interface available and able to accept commands? """
        if self.device.isVirtual:
            return False

        # XXX: TODO: Implement available()
        return True


    # =======================================================================
    # The methods below are the ones shared across subclasses
    # =======================================================================

    def resetConnection(self) -> bool:
        """ Reset the serial connection.

            :return: `True` if the interface connection was reset.
        """
        self._responseBuffer.clear()
        # TODO: Implement resetConnection(). Maybe shut down and recreate client and thread.

        return True


    def close(self) -> bool:
        """ Close the MQTT connection.

            :return: `True` if the interface connection has closed, or was
                already closed.
        """
        if not (self._thread and self._thread.is_alive()):
            return False
        elif not (self.client and self._stopThread.is_set()):
            return False

        self._stopThread.set()
        return True


    def _writeCommand(self,
                      packet: ByteString) -> int:
        """ Transmit a fully formed packet (addressed, HDLC encoded, etc.)
            via MQTT. This is a low-level write to the medium and does not
            do the additional housekeeping that `sendCommand()` does;
            typically, it should not be used directly.

            :param packet: The encoded, packetized, binary `EBMLCommand`
                data.
            :return: The number of bytes written.
        """
        self.client.publish(self.commandTopic, packet)


    def _readResponse(self,
                      timeout: Optional[float] = None,
                      callback: Optional[Callable] = None) -> Union[None, dict]:
        """
        Wait for and retrieve the response to a command. Does not do
        any processing other than (attempting to) decode the EBML payload.

        :param timeout: Time to wait for a valid response. `None` or -1 will
            wait indefinitely.
        :param callback: A function to call each response-checking
            cycle. If the callback returns `True`, the wait for a
            response will be cancelled. The callback function should
            require no arguments.
        :return: A `dict` of response data, or `None` if `callback` caused
            the process to cancel.
        """
        timeout = -1 if timeout is None else timeout
        deadline = time() + timeout

        buf = self._responseBuffer

        while timeout < 0 or time() < deadline:
            if callback is not None and callback():
                return

            if HDLC_BREAK_CHAR in buf:
                idx = buf.index(HDLC_BREAK_CHAR)
                if idx < 1:
                    sleep(.01)
                    continue

                with self.device._busy:
                    packet = buf[:idx]
                    del buf[idx:]

                if packet.startswith(b'\x81\x00'):
                    response = self._decode(packet)
                    self._response = time(), response
                    if 'EBMLResponse' not in response:
                        logger.warning('Response did not contain an EBMLResponse element')
                    return response.get('EBMLResponse', response)
                else:
                    # In the future, there might be other devices on the
                    # bus, so a wrong header might be for a different
                    # address. Ignore.
                    logger.debug("Packet incomplete or has wrong header, ignoring")
            else:
                sleep(.01)

        raise TimeoutError("Timeout waiting for response to serial command")


    def _sendCommand(self,
                     cmd: dict,
                     response: bool = True,
                     timeout: Union[int, float] = 10,
                     interval: float = .25,
                     index: bool = True,
                     callback: Optional[Callable] = None) -> Union[None, dict]:
        """ Send a command to the device and (optionally) retrieve the
            response.

            :param cmd: The command data, as a `dict` that can be encoded as
                EBML data.
            :param response: If `True`, return a response. All serial
                commands generate a response; this is primarily for use with
                commands that potentially cause a reset faster than the
                acknowledgement can be read.
            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
                `None` or -1 will wait indefinitely.
            :param interval: Time (in seconds) between checks for a
                response. Not used by the serial interface.
            :param index: If `True` (default), include an incrementing
                'command index' (for matching responses to commands).
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a
                response will be cancelled. The callback function should
                require no arguments.
            :return: The response dictionary, or `None` if `response` is
                `False`.

            :raise: DeviceTimeout
        """
        timeout = -1 if timeout is None else timeout
        deadline = time() + timeout

        # with self.device._busy:
        try:
            while True:
                if 'EBMLCommand' in cmd and index:
                    self.index += 1
                    cmd['EBMLCommand']['CommandIdx'] = self.index

                packet = self._encode(cmd)
                self.lastCommand = time(), deepcopy(cmd)
                self._writeCommand(packet)

                if timeout == 0:
                    return None

                try:
                    resp = self._readResponse(timeout, callback=callback)
                except Exception as err:
                    if not response:
                        logger.debug('Ignoring anticipated exception because '
                                     'response not required: {!r}'.format(err))
                        self.status = None, None
                        return None
                    else:
                        raise

                if resp:
                    code = resp.get('DeviceStatusCode', 0)
                    msg = resp.get('DeviceStatusMessage')
                    queueDepth = resp.get('CMDQueueDepth', 1)

                    try:
                        code = DeviceStatusCode(code)
                    except ValueError:
                        logger.debug('Received unknown DeviceStatusCode: {}'.format(code))

                    self.status = code, msg

                    if code < 0:
                        # Raise a CommandError or DeviceError. -20 and -30 refer
                        # to bad commands sent by the user.
                        EXC = CommandError if -30 <= code <= -20 else DeviceError
                        raise EXC(code, msg, self.lastCommand[1])

                    if queueDepth == 0:
                        logger.debug('Command queue full, retrying.')
                    else:
                        respIdx = resp.get('ResponseIdx')
                        if respIdx == self.index:
                            return resp if response else None
                        else:
                            logger.debug('Bad ResponseIdx; expected {}, got {}. '
                                         'Retrying.'.format(self.index, respIdx))
                else:
                    queueDepth = 1

                # Failure!
                if timeout > 0 and time() >= deadline:
                    if queueDepth == 0:
                        raise DeviceTimeout('Timed out waiting for opening in command queue')
                    else:
                        raise DeviceTimeout('Timed out waiting for command response')

        except TimeoutError:
            if not response:
                logger.debug('Ignoring timeout waiting for response '
                             'because no response required')
                self.status = None, None
                return None
            else:
                raise


# ===========================================================================
#
# ===========================================================================

class MQTTTester(Thread):
    """ Test rig for connecting a device's SerialCommandInterface to MQTT. It simply
        acts as a bridge between MQTT and a device's command serial port, so it can
        be controlled via `MQTTCommandInterface`.

        Do not use same instance of `Recorder` as the one set up with the
        MQTTCommandInterface`! This expects the device to have a `SerialCommandInterface`.
        You can use the `setup()` function (below) as a convenient way to get things
        started.
    """

    def __init__(self,
                 device,
                 host=MQTT_BROKER,
                 port=MQTT_PORT,
                 topic=MQTT_COMMAND_TOPIC,
                 response=MQTT_RESPONSE_TOPIC,
                 **kwargs):
        super(MQTTTester, self).__init__(**kwargs)
        self.daemon = True
        self.device = device
        self.broker = host, port
        self.commandTopic = topic
        self.responseTopic = response

        self.port = self.device.command.getSerialPort()
        self.client = mqtt.Client()
        self.client.on_connect = self._onMqttConnect
        self.client.on_message = self._onMqttMessage

        self._stop = Event()
        self.start()


    def stop(self):
        self._stop.set()
        self.client.disconnect()


    def _onMqttConnect(self, client, userdata, flags, rc):
        """ Callback to handle the establishment of a MQTT connection.
        """
        if rc == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f"TESTER Connected to broker {self.broker[0]}:{self.broker[1]}")
            client.subscribe(self.commandTopic)
        else:
            logger.error(f"TESTER Connection failed with code: {rc}")


    def _onMqttMessage(self, client, userdata, message):
        """ Callback to handle incoming MQTT messages.
        """
        if message.topic != self.commandTopic:
            logger.debug(f"TESTER Got message on topic {message.topic} (shouldn't happen)")
            return

        logger.debug(f'TESTER got {len(message.payload)} from mqtt: {message.payload!r}')
        self.port.write(message.payload)
        self.port.reset_input_buffer()


    def run(self):
        """ Main loop. Look for incoming serial data and dispatch it over MQTT.
        """
        self.client.connect(*self.broker, 60*60)
        while not self._stop.is_set():
            self.client.loop()
            if self.port.in_waiting:
                waiting = self.port.in_waiting
                data = self.port.read(waiting)
                logger.debug(f'TESTER read {len(data)} of {self.port.in_waiting} bytes from serial port')
                self.client.publish(self.responseTopic, data)
            sleep(.1)


# ===========================================================================
#
# ===========================================================================

def setup(dev=None):
    """ Get a device and set it up with MQTT tester. If a recording device is
        provided, it will have its `SerialCommandInterface` replaced with a
        `MQTTCommandInterface`. This function will also create and start an
        `MQTTTester` thread, which will connect MQTT to the device's actual
         serial port, so the `MQTTCommandInterface` will control the device.

        :param dev: The device to set up. If none is specified, the first
            device found (e.g., lowest drive letter in Windows) will be used.
        :returns: A tuple containing the tester thread and an instance of the
            device with the MQTTCommandInterface.
    """
    from . import getDevices, getRecorder, RECORDERS

    dev = dev or getDevices()[0]

    # Clear the cache and get the device again to get a new instance
    # to which we can apply the MQTTCommandInterface
    path = dev.path
    RECORDERS.clear()
    newdev = getRecorder(path)
    if newdev is dev:
        raise RuntimeError('did not get new recorder instance')

    tester = MQTTTester(newdev)
    dev.command = MQTTCommandInterface(dev)
    dev.command.startMqtt()

    return tester, dev
