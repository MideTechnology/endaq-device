from threading import Event
from time import sleep, time
from typing import Optional, Union

from serial import PortNotOpenError

from .client import synchronized


class SimSerialPort:
    """
    A base class for simulated/vitual serial ports, implementing the core
    subset of `serial.Serial` methods required by `endaq.device`.
    """


    def __init__(self,
                 timeout: Optional[float] = None,
                 write_timeout: Optional[float] = None,
                 maxsize: int = 1024 * 16):
        """ A simulated/vitual serial port, implementing the core subset of
            `serial.Serial` methods required by `endaq.device`.
        """
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.maxsize = maxsize
        self.buffer = bytearray()
        self._is_open = Event()


    def write(self, data: Union[bytes, bytearray]) -> int:
        """ Output the given byte string over the virtual serial port.
        """
        raise NotImplementedError('write() must be implemented by subclasses')


    @synchronized
    def _read(self, size: int) -> bytes:
        """ The actual buffer manipulation. Synchronized.
        """
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result


    def read(self, size: int = 1) -> bytes:
        """
        Read size bytes from the virtual serial port. If a timeout is set it
        may return less characters as requested. With no timeout it will block
        until the requested number of bytes is read.
        """
        if not self._is_open.is_set():
            raise PortNotOpenError()

        if size < 1:
            return b''

        if not self.timeout or len(self.buffer) >= size:
            return self._read(size)

        deadline = time() + (self.timeout or 0)
        while time() < deadline:
            if len(self.buffer) >= size:
                return self._read(size)
            sleep(0.01)

        return self._read(len(self.buffer))


    @synchronized
    def open(self):
        """ Open the virtual port with current settings. """
        self._is_open.set()


    @synchronized
    def close(self):
        """ Close the virtual port. """
        self._is_open.clear()


    @property
    @synchronized
    def is_open(self) -> bool:
        """ Is the virtual port 'open'? """
        return self._is_open.is_set()


    @synchronized
    def reset_input_buffer(self):
        """ Clear input buffer, discarding all that is in the buffer. """
        if not self.is_open:
            raise PortNotOpenError()
        self.buffer.clear()


    @property
    @synchronized
    def in_waiting(self) -> int:
        """ The number of bytes currently in the buffer. """
        return len(self.buffer)

