"""
Classes representing older Mide SlamStick data recorders.
"""

__author__ = "dstokes"
__copyright__ = "Copyright 2022 Mide Technology Corporation"

import os.path
import re

from .base import Recorder
from .endaq import EndaqS

#===============================================================================
#
#===============================================================================


class SlamStickX(Recorder):
    """ A Slam Stick X data recorder from Mide Technology Corporation.
    """
    SN_FORMAT = "SSX%07d"

    # Match all Slam Sticks; this should be last in the list of types to find.
    _NAME_PATTERN = re.compile(r"^Slam Stick.*")

    _FW_UPDATE_FILE = os.path.join("SYSTEM", 'firmware.bin')

    # TODO: This really belongs in the configuration UI
    _POST_CONFIG_MSG = ('When ready...\n'
                        '    1. Disconnect the recorder\n'
                        '    2. Mount to surface\n'
                        '    3. Press the recorder\'s "X" button ')

    manufacturer = "Midé Technology Corporation"
    homepage = "https://endaq.com/collections/endaq-shock-recorders-vibration-data-logger-sensors"


    @property
    def canRecord(self) -> bool:
        """ Can the device record on command? """
        try:
            # Must have version of FW supporting the feature and also be a real
            # device (e.g. has a path).
            if self.isVirtual:
                return False
            return self.firmwareVersion >= 17 and self.path and os.path.isdir(self.path)
        except TypeError:
            return False


    @property
    def canCopyFirmware(self) -> bool:
        """ Can the device get new firmware/bootloader/userpage from a file? """
        # Criteria is the same as `canRecord` (FW version, actual device)
        return self.canRecord


#===============================================================================
#
#===============================================================================

class SlamStickC(SlamStickX):
    """ A Slam Stick C data recorder from Mide Technology Corporation. Also
        sold as enDAQ Sx-D16.
    """
    SN_FORMAT = "SSC%07d"
    _POST_CONFIG_MSG = SlamStickX._POST_CONFIG_MSG.replace(' "X" ', ' "C" ')
    _NAME_PATTERN = re.compile(r"(^Slam Stick C.*)|(^S[234]-D16)")

    @property
    def serial(self) -> str:
        """ The recorder's manufacturer-issued serial number (as string). """
        # Hacky bit to provide Sx-D16 the enDAQ S serial number format.
        if self._sn is None:
            if self.partNumber.endswith('-D16'):
                self.SN_FORMAT = EndaqS.SN_FORMAT
        return super().serial


# ===============================================================================
#
# ===============================================================================

class SlamStickS(SlamStickX):
    """ A Slam Stick S data recorder from Mide Technology Corporation.
    """
    SN_FORMAT = "SSS%07d"
    _POST_CONFIG_MSG = SlamStickX._POST_CONFIG_MSG.replace(' "X" ', ' "S" ')
    _NAME_PATTERN = re.compile("^Slam Stick S.*")
