"""
Classes for testing `client.CommandClient`: a mock `CommandInterface`, and
a minimal subclass of `CommandClient`.
"""

from typing import Any, ByteString, Callable, Optional, Tuple, Union

from endaq.device import Recorder
from endaq.device.client import CommandClient, requires_lock
from endaq.device.command_interfaces import CommandInterface, SerialCommandInterface

from tests.mock_hardware import MockPort

# ===========================================================================
#
# ===========================================================================

class MockClientCommandInterface(SerialCommandInterface):
    """ Minimal `CommandInterface` for the mock `CommandClient`. Commands
        are sent directly to `MockClient.processCommand()`. Instantiate
        using `createMocks()`.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = None
        self.port = MockPort()

    def getSerialPort(self, *args, **kwargs):
        return self.port

    def _writeCommand(self, packet: Union[bytearray, bytes], timeout = 0.5) -> int:
        ...
        self.client.processCommand(packet, self)

    def _readResponse(self,
                      timeout: Optional[Union[int, float]] = None,
                      callback: Optional[Callable] = None) -> Union[None, dict]:
        data = self._decode(self.client._buffer)
        self.client._buffer.clear()
        return data.get('EBMLResponse', data)


class MockClient(CommandClient):
    """ Mock `CommandClient` subclass for testing base functionality.
        Instantiate using `createMocks()`.
    """
    DEVINFO = b'this is fake devinfo'
    CONFIG = b'should fail if unlocked'

    def __init__(self, command_interface: CommandInterface):
        super().__init__(command_interface)
        self._buffer = bytearray()


    def sendResponse(self,
                     recipient: Any,
                     packet: ByteString):
        self._buffer.extend(packet)


    def command_GetInfo_0(self,
                          payload: ByteString,
                          lockId: Optional[int] = None):
        return self.DEVINFO, None, None


    @requires_lock
    def command_GetInfo_5(self,
                          payload: ByteString,
                          lockId: Optional[int] = None):
        """ Example of a `GetInfo` (5: `config.cfg`) that requires the lock
            be set.
        """
        return self.CONFIG, None, None


# ===========================================================================
#
# ===========================================================================

def createMocks(device: Recorder) -> Tuple[CommandInterface, CommandClient]:
    """ Create a mockup `CommandClient`, and a mockup `CommandInterface` to
        test it.

        :param device: Any non-virtual test `Recorder`.
        :returns: The mock `CommandInterface` and `CommandClient`.
    """
    command = MockClientCommandInterface(device)
    client = MockClient(command)
    command.client = client
    return command, client

