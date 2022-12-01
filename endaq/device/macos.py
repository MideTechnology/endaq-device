"""
MacOS-specific functions; primarily filesystem-related. The parent package
imports the appropriate version for the host OS.

TODO: THIS NEEDS TO BE REFACTORED. BASE ON NEXT RELEASE VERSION OF `linux.py`
"""

__all__ = ('deviceChanged', 'getDeviceList', 'getBlockSize', 'getFreeSpace',
           'getDriveInfo', 'readRecorderClock', 'readUncachedFile')

import os

from .linux import getBlockSize, getDriveInfo, readUncachedFile, readRecorderClock

#===============================================================================
#
#===============================================================================


def getDeviceList(types, paths=None):
    """ Get a list of data recorders, as their respective drive letter.
    """
    paths = os.listdir("/Volumes/") if paths is None else paths
    paths = filter(lambda x: x not in ("Mobile Backups", "Macintosh HD"), paths)
    result = []
    for p in paths:
        for t in types:
            if t.isRecorder(p):
                result.append(p)
    return result


_LAST_DEVICES = 0
_LAST_RECORDERS = None


def deviceChanged(recordersOnly, types, clear=False):
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
    
    newDevices = os.listdir("/Volumes/")
    changed = newDevices != _LAST_DEVICES
    _LAST_DEVICES = newDevices

#     if not changed or not recordersOnly:
    if not recordersOnly:
        return changed

    newRecorders = tuple(getDeviceList(types=types))
    changed = newRecorders != _LAST_RECORDERS
    _LAST_RECORDERS = newRecorders
    return changed


def getFreeSpace(path):
    """ Return the free space (in bytes) on a drive.

        :param path: The path to the drive to check. Can be a subdirectory.
        :return: The free space on the drive, in bytes.
        :rtype: int
    """
    # TODO: Make sure this actually works. Should work on all POSIX OSes.
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize
