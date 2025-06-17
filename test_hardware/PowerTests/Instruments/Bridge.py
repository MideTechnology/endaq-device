"""
Class _uart.Bridge to perform low-level actions via Serial on the Otii Power Board.
This class is specifically dedicated to the Otii Power Board v2r1.

Attributes:
    self.gpio_state: (int) Tracks the GPIO register.

Methods:
    __init__(port, verbose): Connect to serial port, configure GPIO pins, query and remember GPIO state.
    static serial_init(port, verbose): Connect to serial port, check connection, and return serial object.
    query(msg, size): Write raw msg to serial and read size bytes.
    read_register(address): Reads a single register. Higher level version of query().
    read_until_termination(): Read bytes sequentially until receive Null or 0x00
    write(data, also_read): Format and send write command from multiple address-data pairs.
    gpio_pin_set(self, pin:int, value: bool): Sets an individual GPIO port.
"""

import serial # pip install pyserial
# ser.write(b'\x57\x02\xAA\x03\xAA\x50\x4F\x00\x50') # original configuration message

# UNUSED: Lists serial port names
def serial_ports():
    import sys
    import glob

    """ Lists serial port names

        :raises EnvironmentError:
            On unsupported or unknown platforms
        :returns:
            A list of the serial ports available on the system
    """
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    return result

class Bridge:
    def __init__(self, port:str, verbose:bool = False):
        # Connect to serial interface
        self.ser = Bridge.serial_init(port, verbose)

        # Pin Configuration
        self.write([(0x02, 0xAA), (0x03, 0xAA)])  # Configure all GPIO pins to PUSH-PULL mode, (see datasheet). don't use: (0x04, 0x00) for set gpio to zero

        # Query and remember GPIO register.
        self.gpio_state = self.read_register(0x04)

        if verbose: print(f'{bin(self.gpio_state) = }')

    @staticmethod
    def serial_init(port: str, verbose:bool = False) -> serial.Serial:
        """
        Connect to serial port, check connection, and return serial object.
        :param port: String port code, ex: "COM7"
        :param verbose: if true, print device response to connection check.
        :return: a reference to the serial object
        """
        ser = serial.Serial(port, 9600, timeout = 1)  # Connect to serial

        # Connection check
        ser.write(b'VP')  # query device name
        cxn = ser.read(16) # read sixteen bits
        if verbose: print(f'Connected to {cxn[:-1].decode()}')
        assert cxn, 'Device not connected'

        return ser

    def query(self, msg: bytes, size:int = 1) -> bytes:
        """
        Write msg to serial and read size bytes.
        :param msg: Bytes object written to device
        :param size: Num of Bytes to read. -1 if unknown
        :return: the response
        """
        self.ser.write(msg)
        return self.ser.read(size) if size > 0 else self.read_until_termination()

    def read_register(self, address: int) -> int:
        """
        Reads a single register. Higher level version of Query
        :param address: address to read
        :return: the register value
        """
        return int(self.query(b'R' + address.to_bytes() + b'P', 1)[0])

    def read_until_termination(self) -> bytes:
        """
        Read bytes sequentially until receive Null or 0x00.
        :return: bytes: Concatenated responses
        """
        output = b''
        r = self.ser.read()
        while r and r[0]:
            output += r
            r = self.ser.read()
        return output

    def write(self, data: list[tuple[int, int]], also_read:bool = False) -> bytes:
        """
        Sends a write command with multiple address-data pairs. Supports a read command on completion.
        :param data: A list of address-data tuples to be sent to device
        :param also_read: if True, a read command will be attempted after writing, and the response will be returned.
        :return: bytes
            If also_read is false, returns the formatted bytestring that was sent to device.
            if also_read is true, returns the serial response as bytestring.
        """
        concat: list[int] = []
        for pair in data:  # flatten list of tuples into one list
            assert len(pair) == 2, 'Each tuple must have format (register, data)'
            concat.extend(pair)

        b = b'W' + bytes(concat) + b'P' # Proper write format from datasheet

        self.ser.write(b)
        if also_read: return self.ser.read()
        return b

    def gpio_pin_set(self, pin:int, value: bool) -> int:
        """
        Sets an individual GPIO port.
        :param pin: target gpio index (0-7)
        :param value: bool
        :return: The updated gpio register
        """
        mask = 2 ** pin  # ex: if pin = 2, mask = 0b100
        self.gpio_state = self.gpio_state | mask if value else ~(~self.gpio_state | mask)
        self.ser.write(b'W\x04' + self.gpio_state.to_bytes() + b'P')
        return self.gpio_state



if __name__ == '__main__':
    ser = Bridge('COM7')