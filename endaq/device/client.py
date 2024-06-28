"""
This module defines base classes for receiving, parsing, and responding to
enDAQ commands in the same way as (or similar to) an enDAQ data recorder.

These are intended for testing `endaq.device` and developing non-embedded
software in the enDAQ ecosystem.
"""

from functools import wraps
from threading import RLock
from typing import Any, ByteString, Optional, Tuple

from .command_interfaces import SerialCommandInterface, CommandError, CRCError, CommandInterface
from .response_codes import DeviceStatusCode


import logging
logger = logging.getLogger('command_client')
logger.setLevel(logging.DEBUG)


# ===========================================================================
#
# ===========================================================================

def synchronized(method):
    """ Decorator for making methods use a lock, modeled after the one in
        Java.
    """
    @wraps(method)
    def wrapped(instance, *args, **kwargs):
        try:
            lock = instance._synchronized_lock
        except AttributeError:
            lock = instance._synchronized_lock = RLock()
        with lock:
            return method(instance, *args, **kwargs)
    return wrapped


def requires_lock(method):
    """ Decorator for command methods that require a `LockID`.
    """
    @wraps(method)
    def wrapped(instance,
                payload: Any,
                         lockId: Optional[int] = None
            ) -> Tuple[dict[str, Any], Optional[DeviceStatusCode], Optional[str]]:
        if lockId != instance.lockId:
            logger.warning(f'Could not run {method.__name__} (mismatched LockID)')
            return {}, DeviceStatusCode.ERR_BAD_LOCK_ID, None
        return method(instance, payload, lockId)
    return wrapped


def dump(data: ByteString, length: int = 8) -> str:
    """ Debugging tool to display `bytes` and `bytearray` values in hex.
    """
    if not length:
        length = len(data)
    return ' '.join(f'{x:02x}' for x in data[:length])


# ===========================================================================
#
# ===========================================================================

class CommandClient:
    """
    A base class for receiving, parsing, and responding to enDAQ commands in
    the same way as (or similar to) an enDAQ data recorder. It is intended
    for testing `endaq.device` and developing non-embedded software in the
    enDAQ ecosystem.
    """

    def __init__(self,
                 command: Optional[CommandInterface] = None,
                 make_crc: bool = True,
                 ignore_crc: bool = False):
        """ A base class for receiving, parsing, and responding to enDAQ
            commands in the same way as (or similar to) an enDAQ data
            recorder.

            :param command: An existing `CommandInterface` to use, if
                required. Defaults to a standard `SerialCommandInterface`.
                Mainly for use in subclasses that override `__init__()`.
            :param make_crc: If `True`, generate CRCs for outgoing responses.
            :param ignore_crc: If `False`, do not validate incoming
                commands.
        """
        if command is None:
            command = SerialCommandInterface(None, make_crc=make_crc, ignore_crc=ignore_crc)
        self.command = command

        # Collect all the class' implemented command methods. See comments
        # near the end for more information.
        self.COMMANDS = {k.partition('_')[-1]: getattr(self, k) for k in dir(self)
                         if k.startswith('command_')}

        self.lockId = b'\x00' * 16


    @property
    def make_crc(self) -> bool:
        """ Generate CRCs for outgoing responses? """
        return self.command.make_crc


    @make_crc.setter
    def make_crc(self, make: bool):
        self.command.make_crc = make


    @property
    def ignore_crc(self) -> bool:
        """ Skip checking the CRCs of incoming commands? """
        return self.command.ignore_crc


    @ignore_crc.setter
    def ignore_crc(self, ignore):
        self.command.ignore_crc = ignore


    @synchronized
    def sendResponse(self,
                     recipient: Any,
                     packet: ByteString):
        """ Transmit a complete, encoded response packet. 
            Must be implemented for each subclass.
        """
        raise NotImplementedError('CommandClient.sendResponse()')


    def sendError(self,
                  recipient: Any,
                  statusCode: DeviceStatusCode,
                  statusMsg: Optional[str] = None):
        """ Helper to transmit a simple error response packet, containing
            nothing other than a status code and optional message, as
            returned when commands could not be parsed/processed.

            :param recipient: The device/computer/connection that sent the
                command. Its type determined by the `CommandClient` subclass.
            :param statusCode: The error status code to send.
            :param statusMsg: Optional descriptive error message.
        """
        response = {'DeviceStatusCode': int(statusCode)}
        if statusMsg:
            response['DeviceStatusMessage'] = statusMsg
        self.sendResponse(recipient, response)


    def decodeCommand(self, packet: ByteString) -> dict[str, Any]:
        """ Decode/parse an incoming command message.
        """
        # Subclasses may override this as needed.
        return self.command._decodeCommand(packet)


    def encodeResponse(self, response: dict[str, Any]) -> ByteString:
        """ Encode an outgoing response.
        """
        # Subclasses may override this as needed.
        return self.command._encodeResponse(response)


    @synchronized
    def processCommand(self,
                       packet: ByteString,
                       sender: Any = None):
        """ Process a command packet.

            :param packet: The raw command message payload.
            :param sender: The device/computer/connection that sent the
                command. Its type determined by the `CommandClient` subclass.
        """
        # Attempt to parse, and generate basic errors for bad packets.
        try:
            command = self.decodeCommand(packet)['EBMLCommand']

        except (CommandError, TypeError, ValueError):
            logger.error(f'processCommand: Bad packet starting with {dump(packet)}')
            self.sendError(sender, DeviceStatusCode.ERR_BAD_PACKET)
            return
        except KeyError:
            logger.error('processCommand: Message did not contain an EBMLCommand element')
            self.sendError(sender, DeviceStatusCode.ERR_INVALID_COMMAND)
            return
        except CRCError:
            logger.error('processCommand: Packet checksum failed')
            self.sendError(sender, DeviceStatusCode.ERR_BAD_CHECKSUM)
            return

        idx = command.pop('CommandIdx', None)
        lockId = command.pop('LockID', None)

        commandName = None
        commandPayload = None
        statusCode = DeviceStatusCode.IDLE
        statusMsg = None

        for k, v in command.items():
            if k in self.COMMANDS:
                commandName = k
                commandPayload = v
                break

        response = {}
        if idx is not None:
            response['ResponseIdx'] = int(idx)
        response['CMDQueueDepth'] = 1

        if commandName:
            try:
                commandFn = self.COMMANDS[commandName]
                reply, replyCode, replyMsg = commandFn(commandPayload, lockId)
                response.update(reply)
                statusCode = replyCode or statusCode
                statusMsg = replyMsg or statusMsg
            except Exception as err:
                logger.error(f'Error processing command {commandName!r}:', exc_info=True)
                statusCode = DeviceStatusCode.ERR_INTERNAL_ERROR
                statusMsg = f"{type(err).__name__}: {err}"
        else:
            statusCode = DeviceStatusCode.ERR_UNKNOWN_COMMAND

        response['DeviceStatusCode'] = int(statusCode)
        if statusMsg:
            response['DeviceStatusMessage'] = statusMsg

        self.sendResponse(sender, self.command._encodeResponse(response))


    def checkLock(self, lockId: ByteString) -> bool:
        """ Verify that a command's LockID matches the object's. Returns
            `True` if the lock IDs match or no lock has been set.
        """
        return not any(self.lockId) or lockId == self.lockId


    # =======================================================================
    # Commands: Methods for each command handled by the `CommandClient`.
    # This base class implements the bare minimum required by something
    # emulating an enDAQ recorder. Presumably, these won't need to be
    # overwritten; subclasses will probably just add command methods.
    #
    # Methods should be named `command_` plus the name of the command's
    # EBML element, (e.g., `command_sendPing()`). `GetInfo` and `SetInfo`
    # have separate methods for each index, and have the index as a suffix
    # (e.g., `command_GetInfo_0`). The base `command_GetInfo()` and
    # `command_SetInfo()` probably won't need to be overridden.
    # 
    # Method arguments:
    #   * payload: The value of the command element. See the schema for the
    #     data type for each command. Note: individual `SetInfo` methods will
    #     get the command's `InfoPayload` value instead of the whole command
    #     dict.
    #   * lockId: The LockID in the command, if any. Only used by commands
    #     that require a lock.
    #
    # Method returns a tuple containing:
    #   * Response dictionary. Commands that have no specific response should
    #     return an empty dict.
    #   * A DeviceStatusCode to return (e.g., if the command generated an
    #     error) which, if not None, overrides the system's DeviceStatusCode.
    #   * A DeviceStatusMessage string which, if not None, overrides the
    #     system's DeviceStatusMessage. 
    # =======================================================================

    def command_SendPing(self, 
                         payload: Any,
                         lockId: Optional[ByteString] = None
            ) -> Tuple[dict[str, Any], Optional[DeviceStatusCode], Optional[str]]:
        """ Handle a ``SendPing`` command (EBML ID 0x5700).

            :param payload: The command element's value.
            :param lockId: The lock ID in the message, if any. 
            :returns: A tuple containing a response dictionary, the response
                DeviceStatusCode (can be `None`), and DeviceStatusMessage
                (can be `None`).
        """
        return {'PingReply': payload}, None, None
    

    def command_GetLockID(self, 
                          payload: ByteString,
                          lockId: Optional[ByteString] = None
            ) -> Tuple[dict[str, Any], Optional[DeviceStatusCode], Optional[str]]:
        """ Handle a `<GetLockID>` command (EBML ID 0x5B00).

            :param payload: The command element's value.
            :param lockId: The lock ID in the message, if any. 
            :returns: A tuple containing a response dictionary, the response
                DeviceStatusCode (can be `None`), and DeviceStatusMessage
                (can be `None`).
        """
        return {'LockID': self.lockId}, None, None


    def command_SetLockID(self, 
                          payload: dict[str, Any],
                          lockId: Optional[ByteString] = None
            ) -> Tuple[dict[str, Any], Optional[DeviceStatusCode], Optional[str]]:
        """ Handle a `<SetLockID>` command (EBML ID 0x5B07).

            :param payload: The command element's value.
            :param lockId: The lock ID in the message, if any. 
            :returns: A tuple containing a response dictionary, the response
                DeviceStatusCode (can be `None`), and DeviceStatusMessage
                (can be `None`).
        """
        try:
            if self.checkLock(payload['CurrentLockID']):
                self.lockId = payload['NewLockID']
                return {'LockID': self.lockId}, None, None
                
            return {}, DeviceStatusCode.ERR_BAD_LOCK_ID, None
        
        except KeyError:
            return {}, DeviceStatusCode.ERR_BAD_PAYLOAD, None


    def command_GetInfo(self,
                        payload: int,
                        lockId: Optional[ByteString] = None
            ) -> Tuple[dict[str, Any], Optional[DeviceStatusCode], Optional[str]]:
        """ Main handler for the `<GetInfo>` command (EBML ID 0x5B00).
        """
        try:
            return self.COMMANDS[f'GetInfo_{payload}'](payload, lockId)
        except KeyError:
            logger.warning(f'No GetInfo for idx {payload!r}')
            return {}, DeviceStatusCode.ERR_BAD_INFO_INDEX, None


    def command_SetInfo(self,
                        payload: dict[str, Any],
                        lockId: Optional[ByteString] = None
            ) -> Tuple[dict[str, Any], Optional[DeviceStatusCode], Optional[str]]:
        """ Main handler for the `<SetInfo>` command (EBML ID 0x5B07).
        """
        try:
            idx = payload['InfoIndex']
            info = payload['InfoPayload']
        except KeyError as err:
            logger.error(f'SetInfo command missing element {err}')
            return {}, DeviceStatusCode.ERR_INVALID_COMMAND, None

        try:
            return self.COMMANDS[f'SetInfo_{idx}'](info, lockId)
        except KeyError:
            logger.warning(f'No SetInfo for idx {idx!r}')

            return {}, DeviceStatusCode.ERR_BAD_INFO_INDEX, None


    @requires_lock
    def command_GetInfo_5(self,
                          payload: ByteString,
                          lockId: Optional[int] = None):
        """ Example of a `GetInfo` (5: `config.cfg`) that requires the lock
            be set.
        """
        raise NotImplementedError('CommandClient.command_GetInfo_5() is only an example')
