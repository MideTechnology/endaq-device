"""
Functions for discovering and instantiating devices that are not connected
and mounted as storage devices.
"""
from typing import Dict, List, Optional

from .base import Recorder
from .command_interfaces import SerialCommandInterface


def getSerialDevices(known: Optional[Dict[int, Recorder]] = None,
                     strict: bool = True) -> List[Recorder]:
    """

        :param known: A dictionary of known `Recorder` instances, keyed by
            device serial number.
        :param strict: If `True`, check the USB serial port VID and PID to
            see if they belong to a known type of device.
        :return:
    """
    if known is None:
        known = {}

    devices = []

    for sn, port in SerialCommandInterface._possibleRecorders(strict=strict):
        if sn in known:
            devices.append(known[sn])
            continue

