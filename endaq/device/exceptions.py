"""
Exceptions raised when interacting with a recording device.
"""

__all__ = ('CommandError', 'CommunicationError', 'ConfigError',
           'ConfigVersionError', 'CRCError', 'DeviceError',
           'DeviceTimeout', 'UnsupportedFeature')


class DeviceError(Exception):
    """ Base class for device-related exceptions. """
    @property
    def errno(self):
        if len(self.args) > 1:
            return self.args[0]
        return None


    def __str__(self):
        if not self.args:
            return repr(self)
        elif len(self.args) == 1:
            return str(self.args[0])
        elif len(self.args) == 2:
            return f'[{self.args[0]}] {self.args[1]}'
        else:
            return f'[{self.args[0]}] {self.args[1:]}'


class CommandError(RuntimeError, DeviceError):
    """ Exception raised by a failure to process a command. """


class CommunicationError(RuntimeError, DeviceError):
    """ Exception raised by a failure to communicate. """


class ConfigError(ValueError, DeviceError):
    """ Exception raised when configuration data is invalid.
    """


class ConfigVersionError(ConfigError, DeviceError):
    """ Exception raised when configuration format doesn't match the recorder
        hardware or firmware version.
    """


class DeviceTimeout(TimeoutError, DeviceError):
    """ Exception raised when a device fails to respond within an expected
        length of time.
    """


class UnsupportedFeature(DeviceError):
    """ Exception raised when a device does not support a given feature
        (e.g., attempting to execute Wi-Fi commands on a device without
        Wi-Fi, or executing a command exclusive to the serial command
        interface over the file-based interface).

        Intended to be instantiated with either a single argument (a message
        string) or with two (the object raising the exception, and the
        offending method).
    """
    @property
    def errno(self):
        return None

    def __str__(self):
        try:
            if len(self.args) == 2:
                return "{}.{}".format(type(self.args[0]).__name__,
                                      self.args[1].__name__)
        except (AttributeError, IndexError, TypeError):
            pass

        return super().__str__()


class CRCError(ValueError):
    """ Exception raised if a packet's CRC16 check fails. """
