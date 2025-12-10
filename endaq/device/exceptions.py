"""
Exceptions raised when interacting with a recording device.
"""

__all__ = ('CommandError', 'CommunicationError', 'ConfigError',
           'ConfigVersionError', 'CRCError', 'DeviceError',
           'DeviceTimeout', 'UnsupportedFeature',
           'ValidationError')

from .response_codes import CommandResponseCode, responsestrings


class DeviceError(Exception):
    """ Base class for device-related exceptions.
    """

    def __init__(self, *args):
        """ Base class for device-related exceptions. """
        # If arguments are (CommandResponseCode, CommandResponseMessage), use
        # default message if the device's response did not include the latter.
        if args and isinstance(args[0], int):
            try:
                errno = CommandResponseCode(args[0])
                msg = args[1] if len(args) > 1 else None
                if not msg:
                    msg = responsestrings.get(errno, None)
                args = errno, msg, *args[2:]
            except ValueError:
                # Probably a code not in the enum
                pass
        super().__init__(*args)


    @property
    def errno(self):
        if len(self.args) > 1 and isinstance(self.args[0], int):
            return self.args[0]
        return None


    def __str__(self):
        if not self.args:
            return super().__str__()

        errno = self.errno

        # Make a CommandResponseCode/DeviceStatusCode pretty
        if isinstance(errno, CommandResponseCode):
            try:
                errno = f'{errno.name} {errno.value}'
            except (AttributeError, IndexError, TypeError):
                pass

        if len(self.args) == 1:
            return str(errno)
        elif len(self.args) == 2:
            return f'[{errno}] {self.args[1]}'
        else:
            return f'[{errno}] {self.args[1:]}'


class CommandError(DeviceError, RuntimeError):
    """ Exception raised by a failure to process a command. """


class CommunicationError(DeviceError, RuntimeError):
    """ Exception raised by a failure to communicate. """


class ConfigError(DeviceError, ValueError):
    """ Exception raised when configuration data is invalid.
    """


class ConfigVersionError(ConfigError, DeviceError):
    """ Exception raised when configuration format doesn't match the recorder
        hardware or firmware version.
    """


class DeviceTimeout(DeviceError, TimeoutError):
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


class ValidationError(ValueError):
    """ Exception raised if a device update, IDE header, or other data fails
        validation.
    """
