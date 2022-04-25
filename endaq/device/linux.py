"""
Linux-specific functions; primarily filesystem-related.
"""

__author__ = "Connor"

import errno
import os
import mmap
import math
import re
from time import time
from typing import ByteString, Tuple

import psutil

from .types import Drive, Epoch, Filename

# ==============================================================================
#
# ==============================================================================


def _getDeviceIds() -> dict:
    idRoot = '/dev/disk/by-id/'
    return {os.path.abspath(idRoot + os.readlink(idRoot + device)): device
            for device in os.listdir(idRoot)}


def _getDeviceLabels() -> dict:
    idRoot = '/dev/disk/by-label/'
    return {os.path.abspath(idRoot + os.readlink(idRoot + device)): device
            for device in os.listdir(idRoot)}


def getDriveInfo(dev: Filename) -> Drive:
    """ Get general device information. Not currently used.
    """
    dev = os.path.realpath(dev)

    disk = [x for x in psutil.disk_partitions()
            if x.mountpoint == dev
            if os.path.split(x.device)[-1] in os.listdir('/dev')][0]
    partName = disk.device

    ids = _getDeviceIds()
    if partName not in ids:
        serial = False
    else:
        serialMatch = re.match(r'(.*MIDE.*)_(\d+)-(.*)', ids[partName])
        if serialMatch is None:
            serial = None
        else:
            serial = serialMatch[2]

    labels = _getDeviceLabels()
    if partName not in labels:
        label = None
    else:
        label = labels[partName]

    return Drive(path=dev, label=label, sn=serial, fs=disk.fstype, type=None)


def readUncachedFile(filename: Filename) -> ByteString:
    """ Read a file, circumventing the disk cache. Returns the data read.
    """
    filename = os.path.realpath(filename)
    root = os.path.dirname(filename)

    if not os.path.isfile(filename):
        raise IOError(errno.ENOENT, 'No such file', filename)

    # For efficiency, this reads entire blocks.
    # Get the file size, rounded up to bytes per filesystem block.
    size = os.path.getsize(filename)
    blockSize = getBlockSize(root)
    readSize = blockSize*math.ceil(size/blockSize)
    m = mmap.mmap(-1, readSize)

    f = os.open(filename, os.O_RDWR | os.O_DIRECT)

    os.lseek(f, 0, os.SEEK_SET)
    os.readv(f, [m])
    m.seek(0)

    return m.read()


def readRecorderClock(clockFile: Filename, pause: bool = True) -> Tuple[Epoch, Epoch]:
    """ Read a (recorder) clock file, circumventing the disk cache. Returns
        the system time and the encoded device time.

        :param clockFile: The full path to the device's clock file (e.g.,
            `/SYSTEM/DEV/CLOCK`).
        :param pause: If `True` (default), wait until the data in the clock
            file changes (e.g. a new tick/second has started) before
            returning. This is a means to maximize accuracy.
        :return: The host time, and the unparsed contents of the device clock
            file.
    """
    root = os.path.abspath(os.path.join(os.path.dirname(clockFile), '..', '..'))

    blockSize = getBlockSize(root)
    m = mmap.mmap(-1, blockSize)

    f = os.open(clockFile, os.O_RDWR | os.O_DIRECT)

    os.lseek(f, 0, os.SEEK_SET)
    os.readv(f, [m])
    lastTime = m.read()

    thisTime = lastTime
    sysTime = time()
    os.lseek(f, 0, os.SEEK_SET)
    m.seek(0)

    if pause:
        while lastTime == thisTime:
            sysTime = time()
            os.readv(f, [m])
            thisTime = m.read()
            sysTime = (time() + sysTime)/2
            os.lseek(f, 0, os.SEEK_SET)
            m.seek(0)

    os.close(f)

    return sysTime, thisTime


# ==============================================================================
#
# ==============================================================================


def getDeviceList(types: dict) -> list:
    """ Get a list of data recorders, as their respective mount points.
    """

    result = set()

    for device, mountpoint, fstype, opts, maxfile, maxpath in psutil.disk_partitions():
        if not os.path.exists(device):
            continue
        for t in types:
            if t.isRecorder(mountpoint):
                result.add(mountpoint)

    return sorted(result)


# Module-level globals for caching last discovered logical drives and recorders
_LAST_DEVICES = None  # List of sdiskpart namedtuples from psutils
_LAST_RECORDERS = None  # tuple of mountpoints of last seen endaq devices


def deviceChanged(recordersOnly: bool, types: dict, clear: bool = False) -> bool:
    """ Returns `True` if a drive has been connected or disconnected since
        the last call to `deviceChanged()`.

        :param recordersOnly: If `False`, any change to the mounted drives
            is reported as a change. If `True`, the mounted drives are checked
            and `True` is only returned if the change occurred to a recorder.
            Checking for recorders only takes marginally more time.
        :param types: A list of known `Recorder` classes to detect.
        :param clear: If `True`, clear the cache of previously-detected
            drives and devices.
    """
    global _LAST_DEVICES, _LAST_RECORDERS

    if clear:
        _LAST_DEVICES = 0
        _LAST_RECORDERS = None

    newDevices = psutil.disk_partitions()
    changed = newDevices != _LAST_DEVICES
    _LAST_DEVICES = newDevices

    # if not changed or not recordersOnly:
    if not recordersOnly:
        return changed

    newRecorders = tuple(getDeviceList(types=types))
    changed = newRecorders != _LAST_RECORDERS
    _LAST_RECORDERS = newRecorders
    return changed


# ==============================================================================
#
# ==============================================================================


def getFreeSpace(path: Filename) -> int:
    """ Return the free space (in bytes) on a drive.

        :param path: The path to the drive to check. Can be a subdirectory.
        :return: The free space on the drive, in bytes.
        :rtype: int
    """
    return psutil.disk_usage(path).free


def getBlockSize(path: Filename) -> int:
    """ Return the bytes per sector and sectors per cluster of a drive.

        :param path: The path to the drive to check. Can be a subdirectory.
        :return: A tuple containing the bytes/sector and sectors/cluster.
    """
    return os.statvfs(path).f_bsize
