"""
Functions for discovering and instantiating devices that are not connected
and mounted as storage devices.
"""

import logging
from typing import Dict, List, Optional

from .base import Recorder, CommandError
from .command_interfaces import SerialCommandInterface
from .devinfo import SerialDeviceInfo
from .response_codes import DeviceStatusCode

logger = logging.getLogger('endaq.device')
logger.setLevel(logging.DEBUG)

def getSerialDevices(known: Optional[Dict[int, Recorder]] = None,
                     strict: bool = True) -> List[Recorder]:
    """ Find all recorders with a serial command interface (and firmware
        that supports retrieving device metadata via that interface).

        :param known: A dictionary of known `Recorder` instances, keyed by
            device serial number.
        :param strict: If `True`, check the USB serial port VID and PID to
            see if they belong to a known type of device.
        :return: A list of `Recorder` instances found.
    """
    from . import RECORDER_TYPES

    if known is None:
        known = {}

    devices = []

    fake = Recorder(None)
    fake.command = SerialCommandInterface(fake)

    for port, sn in SerialCommandInterface._possibleRecorders(strict=strict):
        if sn in known:
            devices.append(known[sn])
            continue

        fake.command.port = None
        fake._snInt, fake._sn = sn, str(sn)

        try:
            info = fake.command._getInfo(0, index=False)
            if not info:
                continue
            for devtype in RECORDER_TYPES:
                if devtype._isRecorder(info):
                    device = devtype(None, devinfo=info)
                    device.command = SerialCommandInterface(device)
                    device._devinfo = SerialDeviceInfo(device)
                    devices.append(device)
                    break
        except CommandError as err:
            if err.errno != DeviceStatusCode.ERR_INVALID_COMMAND:
                logger.debug(f'Unexpected {type(err).__name__} getting info for {sn}: {err}')
            continue

    return devices