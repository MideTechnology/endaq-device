"""
Classes representing older Mide SlamStick data recorders.
"""

__author__ = "dstokes"
__copyright__ = "Copyright 2023 Mide Technology Corporation"

import os.path
import re
from typing import Union

from .base import Recorder
from .endaq import EndaqS
from .types import Filename

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
            if self.productName.endswith('-D16'):
                self.SN_FORMAT = EndaqS.SN_FORMAT
        return Recorder.serial.fget(self)


    @property
    def path(self) -> Union[str, None]:
        return Recorder.path.fget(self)


    @path.setter
    def path(self, dev: Union[Filename, None]):
        """ The recorder's filesystem path (e.g., drive letter or mount point).
        """
        with self._busy:
            Recorder.path.fset(self, dev)
            if self._path:
                if self.getInfo('McuType', '').startswith("STM32"):
                    # HACK: New STM32-based Sx-D16 devices mostly emulate the
                    #  earlier EFM32 series 0 SlamStick C, but update with
                    #  the new firmware packages (i.e., `update.pkg`). This
                    #  is a convenient place to set it.
                    self._FW_UPDATE_FILE = Recorder._FW_UPDATE_FILE


# ===============================================================================
#
# ===============================================================================

class SlamStickS(SlamStickX):
    """ A Slam Stick S data recorder from Mide Technology Corporation.
    """
    SN_FORMAT = "SSS%07d"
    _POST_CONFIG_MSG = SlamStickX._POST_CONFIG_MSG.replace(' "X" ', ' "S" ')
    _NAME_PATTERN = re.compile("^Slam Stick S.*")
