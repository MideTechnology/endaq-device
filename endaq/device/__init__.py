"""
Functions for detecting, identifying, and retrieving information about
data-logging devices.
"""

__author__ = "David Stokes"

import os
import string
from typing import List, Optional, Type, Union

import ebmlite.core
from idelib.dataset import Dataset

from .base import Recorder, os_specific
from .exceptions import ConfigError, ConfigVersionError, DeviceTimeout
from .endaq import EndaqS, EndaqW
from .slamstick import SlamStickX, SlamStickC, SlamStickS
from .types import Filename, Epoch

from . import schemata

__all__ = ('ConfigError', 'ConfigVersionError', 'DeviceTimeout',
           'deviceChanged','findDevice', 'fromRecording', 'getDeviceList',
           'getDevices', 'getRecorder', 'isRecorder', 'onRecorder')

#===============================================================================
# 
#===============================================================================

# Add this package's schema to `ebmlite` schema search path.
SCHEMA_PATH = "{endaq.device}/schemata"
if SCHEMA_PATH not in ebmlite.core.SCHEMA_PATH:
    ebmlite.core.SCHEMA_PATH.insert(0, SCHEMA_PATH)

# Ensure the `idelib` schemata are in the schema path (for idelib <= 3.2.4)
# (remove after next release and requirements updated)
if "{idelib}/schemata" not in ebmlite.core.SCHEMA_PATH:
    ebmlite.core.SCHEMA_PATH.insert(1, "{idelib}/schemata")


# Known classes or recorder. Checks are performed in the specified order, so
# put the ones with more general `isRecorder()` methods (i.e. superclasses)
# after the more specific ones. `SlamStickC` is first, since it is now sold
# as Sx-D16 but has the old SlamStick hardware, but the naming convention
# matches that of `EndaqS`.
# FUTURE: Modularize device type registration, so new ones can be added
#  cleanly (e.g., with a function call like `addRecorderType(class)`?).
RECORDER_TYPES = [SlamStickC, EndaqS, EndaqW, SlamStickS, SlamStickX, Recorder]

# Cache of previously seen recorders, to prevent redundant instantiations.
RECORDERS = {}

# Max number of cached recorders. Probably not needed.
RECORDER_CACHE_SIZE = 100

#===============================================================================
# Platform-specific stuff. 
# TODO: Clean this up, use OS-specific functions directly. 
#===============================================================================


def getRecorder(path: Filename,
                types: Optional[List[Type]] = None,
                update: bool = False,
                strict: bool = True) -> Union[Recorder, None]:
    """ Get a specific recorder by its path.

        :param path: The filesystem path to the recorder's root directory.
        :param types: A list of `Recorder` subclasses to find. Defaults to
            all types.
        :param update: If `True`, update the path of known devices if they
            have changed (e.g., their drive letter or mount point changed
            after a device reset).
        :param strict: If `False`, only the directory structure within `path`
            is used to identify a recorder. If `True`, non-FAT file systems
            will be automatically rejected.
        :return: An instance of a `Recorder` subclass, or `None` if the path
            is not a recorder.
    """
    global RECORDERS

    types = types or RECORDER_TYPES
    dev = None

    for rtype in types:
        if rtype.isRecorder(path, strict=strict):
            # Return existing recorder if it has already been instantiated.
            devhash = rtype._getHash(path)
            if devhash in RECORDERS:
                # Remove existing from cache; it will be re-added at the end
                dev = RECORDERS.pop(devhash)
            else:
                dev = rtype(path, strict=strict)

            if devhash:
                RECORDERS[devhash] = dev

                # Path has changed
                if update and dev.path != path:
                    dev.path = path

            break

    # Remove old cached devices
    if len(RECORDERS) > RECORDER_CACHE_SIZE:
        for k in list(RECORDERS.keys())[:-RECORDER_CACHE_SIZE]:
            del RECORDERS[k]

    return dev


def deviceChanged(recordersOnly: bool = True,
                  types: Optional[List[Type]] = None,
                  clear: bool = False) -> bool:
    """ Returns `True` if a drive has been connected or disconnected since
        the last call to `deviceChanged()`.
        
        :param recordersOnly: If `False`, any change to the mounted drives
            is reported as a change. If `True`, the mounted drives are checked
            and `True` is only returned if the change occurred to a recorder.
            Checking for recorders only takes marginally more time.
        :param types: A list of `Recorder` subclasses to find. Defaults to
            all types.
        :param clear: If `True`, clear the cache of previously-detected
            drives and devices.
    """
    types = types or RECORDER_TYPES
    return os_specific.deviceChanged(recordersOnly, types, clear=clear)


def getDeviceList(types: Optional[List[Type]] = None,
                  strict: bool = True) -> List[Filename]:
    """ Get a list of data recorders, as their respective path (or the drive
        letter under Windows).

        :param types: A list of `Recorder` subclasses to find. Defaults to
            all types.
        :param strict: If `False`, only the directory structure is used
            to identify a recorder. If `True`, non-FAT file systems will
            be automatically rejected.
    """
    types = types or RECORDER_TYPES
    return os_specific.getDeviceList(types, strict=strict)


def getDevices(paths: Optional[List[Filename]] = None,
               types: Optional[List[Type]] = None,
               update: bool = False,
               strict: bool = True) -> List[Recorder]:
    """ Get a list of data recorder objects.
    
        :param paths: A list of specific paths to recording devices.
            Defaults to all found devices (as returned by `getDeviceList()`).
        :param types: A list of `Recorder` subclasses to find. Defaults to
            all types.
        :param update: If `True`, update the path of known devices if they
            have changed (e.g., their drive letter or mount point changed
            after a device reset).
        :param strict: If `False`, only the directory structure is used
            to identify a recorder. If `True`, non-FAT file systems will
            be automatically rejected.
        :return: A list of instances of `Recorder` subclasses.
    """
    global RECORDERS
    types = types or RECORDER_TYPES

    if paths is None:
        paths = getDeviceList(types, strict=strict)
    else:
        if isinstance(paths, (str, bytes, bytearray)):
            paths = [paths]
        paths = [os.path.splitdrive(os.path.realpath(p))[0] for p in paths]

    result = []

    for path in paths:
        dev = getRecorder(path, types=types, update=update, strict=strict)
        if dev is not None:
            result.append(dev)

    return result


def findDevice(sn: Union[str, int],
               paths: Optional[List[Filename]] = None,
               types: Optional[List[Type]] = None) -> Union[Recorder, None]:
    """ Find a specific recorder by serial number.

        :param sn: The serial number of the recorder to find.
        :param paths: A list of specific paths to recording devices.
            Defaults to all found devices (as returned by `getDeviceList()`).
        :param types: A list of `Recorder` subclasses to find. Defaults to
            all types.
        :return: An instance of a `Recorder` subclass representing the
            device with the specified serial number, or `None`.
    """
    types = types or RECORDER_TYPES
    if isinstance(sn, str):
        sn = sn.lstrip(string.ascii_letters+"0")
        if not sn:
            sn = 0
        sn = int(sn)

    for d in getDevices(paths, types):
        if d.serialInt == sn:
            return d

    return None


#===============================================================================
# 
#===============================================================================

def isRecorder(path: Filename,
               types: Optional[List[Type]] = None,
               strict: bool = True) -> bool:
    """ Determine if the given path is a recording device.

        :param path: The filesystem path to check.
        :param types: A list of `Recorder` subclasses to find. Defaults to
            all types.
        :param strict: If `False`, only the directory structure within `path`
            is used to identify a recorder. If `True`, non-FAT file systems
            will be automatically rejected.
    """
    types = types or RECORDER_TYPES
    for t in types:
        if t.isRecorder(path, strict=strict):
            return True
    return False


def onRecorder(path: Filename) -> bool:
    """ Returns the root directory of a recorder from a path to a directory or
        file on that recorder. It can be used to test whether a file is on
        a recorder. `False` is returned if the path is not on a recorder.
        The test is only whether the path refers to a recorder, not whether
        the path or file actually exists; if you need to know if the path
        is valid, perform your own checks first.
        
        :param path: The full path/name of a file.
        :return: The path to the root directory of a recorder (e.g. the drive
            letter in Windows) if the path is to a subdirectory on a recording 
            device, `False` if not.
    """
    oldp = None
    path = os.path.realpath(path)
    while path != oldp:
        if isRecorder(path):
            return path
        oldp = path
        path = os.path.dirname(path)
    return False


def fromRecording(doc: Dataset) -> Recorder:
    """ Create a 'virtual' recorder from the data contained in a recording
        file.
    """
    productName = doc.recorderInfo.get('ProductName')
    if not productName:
        productName = doc.recorderInfo.get('PartNumber')
    if productName is None:
        raise TypeError("Could not create virtual recorder from file (no ProductName)")
    recType = None
    for rec in RECORDER_TYPES:
        if rec._matchName(productName):
            recType = rec
            break
    if recType is None:
        return None
    return recType.fromRecording(doc)
