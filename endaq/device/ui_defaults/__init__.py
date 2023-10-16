"""
Default CONFIG.UI data, for devices (mostly virtual) that do not have it.
CONFIG.UI data defines the configuration GUI layout, as well as provides
information for converting values when reading and writing configuration
data.
"""

from importlib import import_module
import logging
from typing import Union

logger = logging.getLogger('endaq.device')

# Special-case mapping of non-standard part numbers to default ConfigUI
# modules (special/custom/OEM builds, etc.)
# FUTURE: Add pattern matching (regex/glob)?
SPECIAL_CASES = {
    'S3-D16': 'LOG-0003-016G',
    'SF-DR4-01': 'W8-R2000D40',
    'SF-DR4-02': 'Sx-E2000D40',
    'SF-DR4-03': 'W8-R2000D40',
    'SF-DR4-04': 'Sx-E100D40',
}


def _getConfigUI(name: str) -> Union[bytes, None]:
    """ Get the default ConfigUI data from a module.

        :param name: The name of the module (typically matches a device's
            part number).
        :return: The raw binary ConfigUI EBML if there is a matching module,
            or `None`.
    """
    try:
        name = name.replace('-', '_')
        mod = import_module("." + name, __package__)
        return mod.DEFAULT_CONFIG_UI
    except ImportError:
        return None


def _getGenericName(pn: str) -> str:
    """ Get a potential module name for a product without a unique ConfigUI
        file for its part number. This is typically a 'generic' one, or
        a special case device name.

        :param pn: A product part number without a directly corresponding
            default ConfigUI module.
        :return: An alternative part number that may (or may not) have a
            corresponding default ConfigUI module.
    """
    if pn in SPECIAL_CASES:
        return SPECIAL_CASES[pn]

    elif pn.startswith('LOG-'):
        # For ancient Slam Stick X recorders without digital accel
        return pn + "-DC"

    family, sep, model = pn.partition('-')
    return "{}x{}{}".format(family[0], sep, model)


def getDefaultConfigUI(device) -> Union[str, None]:
    """ Attempt to find canned 'default' ConfigUI file for the device,
        based on its part number.

        :param device: The device in need of default ConfigUI data.
        :return: The raw binary ConfigUI EBML if there is a corresponding
            module, or `None`.
    """
    # FUTURE: Also have default variants based on HwRev and/or FwRev?
    uiName = device.partNumber
    ui = _getConfigUI(uiName)
    if not ui:
        ui = _getConfigUI(_getGenericName(uiName))

    if not ui:
        logger.warning("Could not find default ConfigUI for {}, using default".format(device.partNumber))
        ui = _getConfigUI('default')

    return ui
