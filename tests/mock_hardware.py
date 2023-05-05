"""
Components for replacing hardware-dependent functionality, for testing purely
in software.
"""

import endaq.device
from endaq.device.command_interfaces import CommandInterface, FileCommandInterface
from endaq.device.hdlc import hdlc_encode


class MockCommandIO:
    """ Replacement for a `CommandInterface`'s low-level command-writing and
        response-reading. It allows testing without hardware, the command
        packet can be inspected, and an arbitrary responce can be specified.

        Usage (`dev` is an instance of an `endaq.device.Recorder` subclass):

            mock_io = MockCommandIO(dev)
            mock_io.response = mock_io.encodeResponse({'EBMLResponse':
                                                       {'ResponseIdx': 1,
                                                        'CMDQueueDepth': 1,
                                                        'DeviceStatusCode': 0,
                                                        'PingReply': bytearray(b'hello')}},
                                                      resultcode=0)
            assert dev.command.ping() == bytearray(b'hello')

    """


    def __init__(self, device: endaq.device.Recorder):
        """ Replacement for a device's `CommandInterface`.

            :param device: The device under test.
        """
        self.device = device
        self.command = None  # The last command sent by the device
        self.response = None  # The raw data to send in response
        self.responseArgs = None

        device.command._writeCommand = self.writeCommand
        device.command._readResponse = self.readResponse
        device._getSerialPort = self.getSerialPort


    def encodeResponse(self, response: dict, resultcode: int = 0) -> bytearray:
        """ Encode a dictionary containing a device response into the raw
            format expected of the device.

            :param response: The response dictionary.
            :param resultcode: The Corbus response code. Not applicable to
                `FileCommandInterface`. Non-zero is an error.
            :return: The response as raw binary.
        """
        response = CommandInterface._encode(self.device.command, response)
        if isinstance(self.device.command, FileCommandInterface):
            return response

        response = bytearray([0x81, 0x00, resultcode]) + response
        return hdlc_encode(response)


    def getSerialPort(self, *args, **kwargs):
        """ A replacement for the `_getSerialPort()` of the `CommandInterface`
            under test. It does nothing.
        """
        return None


    def writeCommand(self, packet):
        """ A replacement for the `_writeCommand()` of the `CommandInterface`
            under test. It just stores the raw packet for inspection.
        """
        self.command = packet
        return len(packet)


    def readResponse(self, timeout=None, callback=None):
        """ A replacement for the `_readResponse()` of the `CommandInterface`
            under test. It stores the calling arguments for inspection and
            returns `self.response`.
        """
        self.responseArgs = (timeout, callback)
        return self.response

