"""
Classes representing an enDAQ Gateway device: hardware and/or software
running an MQTT broker and device management, and functioning as a
network hub/AP/bridge/etc.
"""

from ebmlite import loadSchema
from endaq.device.base import Recorder
from endaq.device.mqtt.discovery import splitServiceName
from endaq.device.util import synchronized

import logging
logger = logging.getLogger(__name__)

__all__ = ('Gateway',)


# ===============================================================================
#
# ===============================================================================

class Gateway(Recorder):
    """
    An enDAQ Gateway device: hardware and/or software running an MQTT broker
    and device management, optionally functioning as a network hub (AP, bridge,
    etc.).
    """

    SN_FORMAT = "G%07d"

    @classmethod
    def _isRecorder(cls,
                    info: bytes) -> bool:
        """ Test whether the given ``DEVINFO`` describes a device matching
            this class. Used internally by `isRecorder()` and externally when
            instantiating remote devices.

            :param info: Raw device metadata, as read from a ``DEVINFO``
                file, retrieved via a command interface, etc.
            :return: `True` if the info is a match for this `Recorder` class.
        """
        try:
            if not info:
                return False
            devinfo = loadSchema('mide_ide.xml').loads(info).dump()
            uid = devinfo['RecordingProperties']['RecorderInfo']['RecorderTypeUID']
            return uid & 0xa0000000

        except (KeyError, IOError) as err:
            logger.debug("Gateway._isRecorder() raised a possibly-allowed exception: %r" % err)
            return False


    @synchronized
    def __repr__(self) -> str:
        """ Return repr(self). """
        try:
            name = self.partNumber or self.productName

            try:
                if self.name:
                    base, _ = splitServiceName(self.name)
                    name = f'{name} "{base}"'
            except RecursionError:
                # Some debugging tools can indirectly call __repr__ in race
                # condition and get stuck in a loop trying to resolve `name`
                logger.warning('RecursionError getting name in __repr__()!', exc_info=True)

            return f'<{type(self).__name__} {name} SN:{self.serial})>'

        except Exception as err:
            # repr should never completely fail; use default object repr.
            logger.warning(f'Error in {type(self).__name__}.__repr__(): {err!r}', exc_info=True)
            return object.__repr__(self)


    @property
    def canRecord(self) -> bool:
        """ Can the device record on command? Not applicable to non-sensors.
        """
        return False
