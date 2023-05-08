"""
Components for replacing hardware-dependent functionality, for testing purely
in software.
"""

import endaq.device
from endaq.device.command_interfaces import CommandInterface, FileCommandInterface
from endaq.device.hdlc import hdlc_encode


class MockPort:
    """
    A fake serial port. It collects data written to it, and reading it
    returns a canned response.

    Note: This only implements a subset of `serial.Serial` methods. More may
    need to be added if changes are made to `SerialCommandInterface`.
    """

    def __init__(self, response=b'', chunksize=None):
        """ A fake serial port. Arguments are also attributes which
            can be set at any time.

            :param response: Data to be returned on `read()`.
            :param chunksize: The number of bytes returned each read, to
                simulate data arriving during the `read()`.
        """
        self.is_open = False
        self.timeout = 0

        self.input = b''
        self.response = response
        self.chunkSize = chunksize

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def read(self, size=None):
        size = size or len(self.response)
        if self.chunkSize:
            size = min(size, self.chunkSize)

        result = self.response[:size]
        self.data = self.response[size:]
        return result

    def write(self, data):
        self.input += data

    def flushInput(self):
        pass

    def flushOutput(self):
        pass

    def flush(self):
        pass

    @property
    def in_waiting(self):
        return len(self.response)


class MockCommandFileIO:
    """ Replaces the low-level communication in a device's `FileCommandInterface`.
        It allows testing without hardware, the command packet can be inspected,
        and an arbitrary response can be generated.

        Specifically, `MockCommandFileIO` replaces the COMMAND file writing
        and RESPONSE file reading methods of the device's `FileCommandInterface`
        instance. It also provides a method for encoding responses as returned
        via the serial command interface.

        Usage (`dev` is an instance of an `endaq.device.Recorder` subclass with
        a `FileCommandInterface`):

            mock_io = MockCommandFileIO(dev)
            mock_io.response = mock_io.encodeResponse(<EBMLResponse dict>)
    """

    def __init__(self, device: endaq.device.Recorder):
        """ Replacement for a device's `FileCommandInterface`.

            :param device: The device under test.
        """
        self.device = device
        device.command._writeCommand = self._writeCommand
        device.command._readResponse = self._readResponse

        self.response = None  # The raw data to send in response


    def _writeCommand(self, packet):
        """ A replacement for the `_writeCommand()` of the `CommandInterface`
            under test. It just stores the raw packet for inspection.
        """
        self.command = packet
        return len(packet)


    def _readResponse(self, timeout=None, callback=None):
        """ A replacement for the `_readResponse()` of the `CommandInterface`
            under test. It stores the calling arguments for inspection and
            returns `self.response`.
        """
        self.responseArgs = (timeout, callback)
        return self.response


    def encodeResponse(self, response: dict) -> bytearray:
        """ Utility method to encode a dictionary containing a device
            response into the raw format expected of the device.

            :param response: The response dictionary.
            :return: The response as raw binary.
        """
        return CommandInterface._encode(self.device.command, response, checkSize=False)



class MockCommandSerialIO:
    """ Replaces the low-level communication in a device's
        `SerialCommandInterface`. It allows testing without hardware, the
        command packet can be inspected, and an arbitrary response can be
        specified.

        Specifically, `MockCommandSerialIO` replaces the device's
        `SerialCommandInterface`serial port instance with an instance of
        `MockPort`, and provides a utility method for encoding responses as
        returned via the serial command interface.

        Usage (`dev` is an instance of an `endaq.device.Recorder` subclass with
        a `SerialCommandInterface`):

            mock_io = MockCommandSerialIO(dev)
            mock_io.response = mock_io.encodeResponse({'EBMLResponse':
                                                       {'ResponseIdx': dev.command.index + 1,
                                                        'CMDQueueDepth': 1,
                                                        'DeviceStatusCode': 0,
                                                        'PingReply': bytearray(b'hello')}},
                                                      resultcode=0)
            assert dev.command.ping() == bytearray(b'hello')

    """

    def __init__(self, device: endaq.device.Recorder):
        """ Replacement for a device's `SerialCommandInterface`.

            :param device: The device under test.
        """
        self.device = device
        self.port = MockPort()
        device.command.port = self.port
        device.command.getSerialPort = self.getSerialPort


    @property
    def response(self):
        return self.port.response


    @response.setter
    def response(self, data):
        self.port.response = data


    def encodeResponse(self, response: dict, resultcode: int = 0) -> bytearray:
        """ Utility method to encode a dictionary containing a device
            response into the raw format expected from the device.

            :param response: The response dictionary.
            :param resultcode: The Corbus response code. Not applicable to
                `FileCommandInterface`. Non-zero is an error.
            :return: The response as raw binary.
        """
        response = CommandInterface._encode(self.device.command, response, checkSize=False)
        return hdlc_encode(bytearray([0x81, 0x00, resultcode]) + response)


    def getSerialPort(self, *args, **kwargs):
        """ A replacement for the `_getSerialPort()` of the `CommandInterface`
            under test. It does nothing but return the object's `MockPort`
            instance.
        """
        return self.port


def applyMockCommandIO(device):
    """ Apply the appropriate mock IO to the device's `command` object.
    """
    if not isinstance(device.command, CommandInterface):
        raise TypeError(f'{device} had invalid command interface: '
                        f'{device.command!r}')

    if isinstance(device.command, FileCommandInterface):
        return MockCommandFileIO(device)
    else:
        return MockCommandSerialIO(device)
