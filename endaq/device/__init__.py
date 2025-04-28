"""
Functions for detecting, identifying, and retrieving information about
data-logging devices.
"""

__author__ = "David Stokes"
__copyright__ = "Copyright 2024 Mide Technology Corporation"

import os
from pathlib import Path
import string
from threading import RLock
from typing import Dict, List, Optional, Union
from weakref import WeakValueDictionary

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

import ebmlite.core
from idelib.dataset import Dataset

from .base import Recorder, NonRecorder, os_specific
from .command_interfaces import SerialCommandInterface
from .devinfo import SerialDeviceInfo
from .exceptions import *
from .endaq import EndaqS, EndaqW
from .response_codes import DeviceStatusCode
from .slamstick import SlamStickX, SlamStickC, SlamStickS
from .types import Drive, Filename, Epoch

# ============================================================================
#
# ============================================================================

__version__ = "1.4.0"

__all__ = ('CommandError', 'ConfigError', 'ConfigVersionError',
           'DeviceError', 'DeviceTimeout', 'UnsupportedFeature',
           'deviceChanged', 'findDevice', 'fromRecording',
           'getDevices', 'getRecorder', 'isRecorder', 'onRecorder',
           'Recorder', 'EndaqS', 'EndaqW', 'SlamStickX', 'SlamStickC',
           'SlamStickS')

# ============================================================================
# EBML schema path modification
# ============================================================================

SCHEMA_PATH = "{endaq.device}/schemata"

# Ensure the `idelib` schemata are in the schema path (for idelib <= 3.2.4)
if "{idelib}/schemata" not in ebmlite.core.SCHEMA_PATH:
    ebmlite.core.SCHEMA_PATH.insert(0, "{idelib}/schemata")

# Add this package's schema to `ebmlite` schema search path, after
# `idelib`'s. This is a workaround for issue with legacy schema installed by
# earlier versions (can probably be removed after beta).
if SCHEMA_PATH not in ebmlite.core.SCHEMA_PATH:
    _idx = ebmlite.core.SCHEMA_PATH.index("{idelib}/schemata") + 1
    ebmlite.core.SCHEMA_PATH.insert(_idx, SCHEMA_PATH)

# ============================================================================
#
# ============================================================================

# Known classes or recorder. Checks are performed in the specified order, so
# put the ones with more general `isRecorder()` methods (i.e. superclasses)
# after the more specific ones. `SlamStickC` is first, since it is now sold
# as Sx-D16 but has the old SlamStick hardware, but the naming convention
# matches that of `EndaqS`. The base `Recorder` should be last.
RECORDER_TYPES = [SlamStickC, EndaqS, EndaqW, SlamStickS, SlamStickX, Recorder]

# Cache of previously seen recorders, to prevent redundant instantiations.
# Keyed by the hash of the recorders DEVINFO (or equivalent).
RECORDERS = {}

# Another cache of recorders, keyed by serial number. Used when discovering
# remote devices that don't immediately have DEVINFO accessible.
RECORDERS_BY_SN = WeakValueDictionary()

# Max number of cached recorders. Probably not needed, but just in case.
RECORDER_CACHE_SIZE = 100

# Lock to prevent contention (primarily with the recorder cache). Several
# classes have their own 'busy' locks as well.
_module_busy = RLock()


# ============================================================================
# Platform-specific stuff. 
# ============================================================================

def getRecorder(path: Filename,
                update: bool = False,
                strict: bool = True) -> Union[Recorder, None]:
    """ Get a specific recorder by its path.

        :param path: The filesystem path to the recorder's root directory.
        :param update: If `True`, update the path of known devices if they
            have changed (e.g., their drive letter or mount point changed
            after a device reset).
        :param strict: If `False`, only the directory structure within `path`
            is used to identify a recorder. If `True`, non-FAT file systems
            will be automatically rejected.
        :return: An instance of a :class:`~.endaq.device.Recorder` subclass,
            or `None` if the path is not a recorder.
    """
    global RECORDERS, RECORDERS_BY_SN

    dev = None

    with _module_busy:
        for rtype in RECORDER_TYPES:
            if rtype.isRecorder(path, strict=strict):
                # Get existing recorder if it has already been instantiated.
                devhash = rtype._getHash(path)
                dev = RECORDERS.pop(devhash, None)
                if not dev:
                    dev = rtype(path, strict=strict)
                else:
                    # Clear DEVINFO-getter, in case device was previously remote
                    dev._devinfo = None

                if devhash:
                    RECORDERS[devhash] = dev

                    # Path has changed. Note that the hash does not include
                    # path, in case a device rebooted and remounted with a
                    # different mount point/drive letter.
                    if update and dev.path != path:
                        dev.path = path

                RECORDERS_BY_SN[dev.serialInt] = dev

                break

        # Remove old cached devices. Ordered dictionaries assumed!
        if len(RECORDERS) > RECORDER_CACHE_SIZE:
            for k in list(RECORDERS.keys())[-RECORDER_CACHE_SIZE:]:
                del RECORDERS[k]

        return dev


def deviceChanged(recordersOnly: bool = True,
                  clear: bool = False) -> bool:
    """ Returns `True` if a drive has been connected or disconnected since
        the last call to :meth:`~.endaq.device.deviceChanged`.
        
        :param recordersOnly: If `False`, any change to the mounted drives
            is reported as a change. If `True`, the mounted drives are checked
            and `True` is only returned if the change occurred to a recorder.
            Checking for recorders only takes marginally more time.
        :param clear: If `True`, clear the cache of previously-detected
            drives and devices.
    """
    return os_specific.deviceChanged(recordersOnly, RECORDER_TYPES, clear=clear)


def getDeviceList(strict: bool = True) -> List[Drive]:
    """ Get a list of local data recorders, as their respective path (or the
        drive letter under Windows).

        :param strict: If `False`, only the directory structure is used
            to identify a recorder. If `True`, non-FAT file systems will
            be automatically rejected.
        :return: A list of `Drive` objects (named tuples containing the
            drive path, label, and other low-level filesystem info).
    """
    return os_specific.getDeviceList(RECORDER_TYPES, strict=strict)


def getDevices(paths: Optional[List[Filename]] = None,
               unmounted: bool = True,
               update: bool = True,
               strict: bool = True) -> List[Recorder]:
    """ Get a list of data recorder objects.
    
        :param paths: A list of specific paths to recording devices.
            Defaults to all found devices (as returned by
            :meth:`~.endaq.device.getDeviceList`).
        :param unmounted: If `True`, include devices connected by USB
            and responsive to commands but not appearing as drives.
            Note: Not all devices/firmware versions support this.
        :param update: If `True`, update the path of known devices if they
            have changed (e.g., their drive letter or mount point changed
            after a device reset).
        :param strict: If `False`, only the directory structure is used
            to identify a recorder. If `True`, non-FAT file systems and
            non-removable media will be automatically rejected.
        :return: A list of instances of `Recorder` subclasses.
    """
    global RECORDERS, RECORDERS_BY_SN

    with _module_busy:
        if paths is None:
            paths = getDeviceList(strict=strict)
        else:
            if isinstance(paths, (str, bytes, bytearray, Path)):
                paths = [paths]

        result = set()

        for path in paths:
            dev = getRecorder(path, update=update, strict=strict)
            if dev is not None:
                result.add(dev)

        if unmounted:
            for dev in getSerialDevices(known=RECORDERS_BY_SN):
                if not dev.available:
                    dev.path = None
                result.add(dev)
                RECORDERS.pop(hash(dev), None)
                RECORDERS[hash(dev)] = dev
                RECORDERS_BY_SN[dev.serialInt] = dev

        return sorted(result, key=lambda x: x.path or '\uffff')


def findDevice(sn: Optional[Union[str, int]] = None,
               chipId: Optional[Union[str, int]] = None,
               paths: Optional[List[Filename]] = None,
               unmounted: bool = False,
               update: bool = False,
               strict: bool = True) -> Union[Recorder, None]:
    """ Find a specific recorder by serial number or unique chip ID. One or
        the other must be provided, but not both. Note that early firmware
        versions do not report the device's chip ID.

        :param sn: The serial number of the recorder to find. Cannot be used
            with `chipId`. It can be an integer or a formatted serial number
            string (e.g., `12345` or `"S00012345"`).
        :param chipId: The chip ID of the recorder to find. Cannot be used
            with `sn`. It can be an integer or a hex string. Note that
            `chipId` cannot be used to find SlamStick and older enDAQ S
            devices (prior to hardware revision 2.0), as they do not report
            their chip ID.
        :param paths: A list of specific paths to recording devices.
            Defaults to all found devices (as returned by
            :meth:`~.endaq.device.getDeviceList`).
        :param unmounted: If `True`, include devices connected by USB
            and responsive to commands but not appearing as drives.
            Note: Not all devices/firmware versions support this.
        :param update: If `True`, update the path of known devices if they
            have changed (e.g., their drive letter or mount point changed
            after a device reset).
        :param strict: If `False`, only the directory structure is used
            to identify a recorder. If `True`, non-FAT file systems will
            be automatically rejected.
        :return: An instance of a :class:`~.endaq.device.Recorder` subclass
            representing the device with the specified serial number or chip
            ID, or `None` if it cannot be found.
    """
    with _module_busy:
        if sn and chipId:
            raise ValueError('Either a serial number or chip ID is required, not both')
        elif sn is None and chipId is None:
            raise ValueError('Either a serial number or chip ID is required')

        if isinstance(sn, str):
            sn = sn.lstrip(string.ascii_letters+"0")
            if not sn:
                sn = 0
            sn = int(sn)

        if isinstance(chipId, str):
            chipId = int(chipId, 16)

        for d in getDevices(paths, update=update, strict=strict, unmounted=unmounted):
            if sn is not None and d.serialInt == sn:
                return d
            elif chipId is not None and d.chipId == chipId:
                return d

        return None


# ============================================================================
# 
# ============================================================================

def isRecorder(path: Filename,
               strict: bool = True) -> bool:
    """ Determine if the given path is a recording device.

        :param path: The filesystem path to check.
        :param strict: If `False`, only the directory structure within `path`
            is used to identify a recorder. If `True`, non-FAT file systems
            will be automatically rejected.
    """
    with _module_busy:
        for t in RECORDER_TYPES:
            if t.isRecorder(path, strict=strict):
                return True
        return False


def onRecorder(path: Filename, strict: bool = True) -> bool:
    """ Returns the root directory of a recorder from a path to a directory or
        file on that recorder. It can be used to test whether a file is on
        a recorder. `False` is returned if the path is not on a recorder.
        The test is only whether the path refers to a recorder, not whether
        the path or file actually exists; if you need to know if the path
        is valid, perform your own checks first.
        
        :param path: The full path/name of a file.
        :param strict: If `False`, only the directory structure within `path`
            is used to identify a recorder. If `True`, non-FAT file systems
            will be automatically rejected.
        :return: The path to the root directory of a recorder (e.g. the drive
            letter in Windows) if the path is to a subdirectory on a recording 
            device, `False` if not.
    """
    oldp = None
    path = os.path.realpath(path)
    while path != oldp:
        if isRecorder(path, strict=strict):
            return path
        oldp = path
        path = os.path.dirname(path)
    return False


def fromRecording(doc: Dataset) -> Recorder:
    """ Create a 'virtual' recorder from the data contained in a recording
        file.

        :param doc: An imported IDE recording. Note that very old IDE files
            may not contain the metadata requires to create a `virtual`
            device.
    """
    productName = doc.recorderInfo.get('ProductName')
    if not productName:
        productName = doc.recorderInfo.get('PartNumber')
    if productName is None:
        raise TypeError("Could not create virtual recorder from file "
                        "(no ProductName or PartNumber in metadata)")
    recType = None
    for rec in RECORDER_TYPES:
        if rec._matchName(productName):
            recType = rec
            break
    if recType is None:
        return None
    return recType.fromRecording(doc)


# ============================================================================
# 
# ============================================================================

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
    if known is None:
        known = {}

    devices = []

    # Dummy recorder and command interface to retrieve DEVINFO
    fake = NonRecorder()
    fake.command = SerialCommandInterface(fake)

    for port, sn in SerialCommandInterface._possibleRecorders(strict=strict):
        if sn in known:
            devices.append(known[sn])
            continue

        fake.command.port = None
        fake._snInt, fake._sn = sn, str(sn)

        with _module_busy:
            try:
                logger.debug(f'Getting info for SN {sn} via serial')
                info = fake.command._getInfo(0, index=False)
                if not info:
                    logger.debug(f'No info returned by SN {sn}, continuing')
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
