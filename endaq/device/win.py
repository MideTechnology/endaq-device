"""
Windows-specific functions; primarily filesystem-related.
"""

__author__ = "dstokes"
__copyright__ = "Copyright 2022 Mide Technology Corporation"

import ctypes
import errno
import os
from pathlib import Path
import sys
from time import time
from typing import ByteString, List, Optional, Tuple

from .types import Drive, Epoch, Filename

# ==============================================================================
#
# ==============================================================================

if 'win' in sys.platform and sys.platform != 'darwin':
    kernel32 = ctypes.windll.kernel32
    import pywintypes
    import win32api
    import win32con
    import win32file
else:
    kernel32 = None


def getDriveInfo(dev: Filename) -> Drive:
    """ Get general device information. Not currently used.
    """
    dev = os.path.realpath(str(dev))

    volumeNameBuffer = ctypes.create_unicode_buffer(1024)
    fileSystemNameBuffer = ctypes.create_unicode_buffer(1024)
    serial_number = ctypes.c_uint(0)
    # file_system_flags =  ctypes.c_uint(0)
    kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(dev),
        volumeNameBuffer,
        ctypes.sizeof(volumeNameBuffer),
        ctypes.byref(serial_number),
        None,  # max_component_length,
        None,  # ctypes.byref(file_system_flags),
        fileSystemNameBuffer,
        ctypes.sizeof(fileSystemNameBuffer)
    )

    try:
        sn = "%08X" % serial_number.value
    except (AttributeError, TypeError):
        sn = None

    try:
        fs = fileSystemNameBuffer.value
    except AttributeError:
        fs = None

    return Drive(path=dev, label=volumeNameBuffer.value, sn=sn,
                 fs=fs, type=win32file.GetDriveType(dev))
    

def readUncachedFile(filename: Filename) -> ByteString:
    """ Read a file, circumventing the disk cache. Returns the data read.
    """
    if isinstance(filename, Path):
        filename = str(filename)

    filename = os.path.realpath(filename)
    root = os.path.dirname(filename)

    if not os.path.isfile(filename):
        raise IOError(errno.ENOENT, 'No such file', filename)

    # For efficiency, this reads entire blocks.
    # Get the file size, rounded up to bytes per filesystem block.
    size = os.path.getsize(filename)
    spc, bps, _fc, _tc  = win32file.GetDiskFreeSpace(root)
    bpc = spc * bps

    if size > bpc:
        blocks = size // bpc
        if bpc % size:
            blocks += 1
        size = blocks * bpc
    else:
        size = bpc

    try:
        f1 = win32file.CreateFile(filename,
                                  win32con.GENERIC_READ, 
                                  win32con.FILE_SHARE_READ,
                                  None,
                                  win32con.OPEN_EXISTING,
                                  win32con.FILE_FLAG_NO_BUFFERING,
                                  0)
        _hr, data = win32file.ReadFile(f1, int(size))
        win32api.CloseHandle(f1)        
        return data
    
    except pywintypes.error as err: 
        raise IOError(err.strerror)


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
    
    try:
        f1 = win32file.CreateFile(clockFile,
                                  win32con.GENERIC_READ, 
                                  win32con.FILE_SHARE_READ,
                                  None,
                                  win32con.OPEN_EXISTING,
                                  win32con.FILE_FLAG_NO_BUFFERING,
                                  0)
    except pywintypes.error as err:
        raise IOError(err.strerror)

    # For efficiency, this reads entire blocks.
    # It is assumed the clock value is smaller than one block.
    spc, bps, _fc, _tc  = win32file.GetDiskFreeSpace(root)
    bpc = spc * bps

    _hr, lastTime = win32file.ReadFile(f1, bpc)
    thisTime = lastTime
    sysTime = time()
    win32file.SetFilePointer(f1, 0, win32file.FILE_BEGIN)

    if pause:
        while lastTime == thisTime:
            sysTime = time()
            _hr, thisTime = win32file.ReadFile(f1, bpc)
            sysTime = (time() + sysTime)/2
            win32file.SetFilePointer(f1, 0, win32file.FILE_BEGIN)

    win32api.CloseHandle(f1)
    return sysTime, thisTime

# ==============================================================================
# 
# ==============================================================================


def getDeviceList(types: dict) -> List[Drive]:
    """ Get a list of data recorders, as their respective drive letter.
    """
    drivebits = kernel32.GetLogicalDrives()
    result = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if drivebits & 1:
            driveLetter = '%s:\\' % letter
            devtype = win32file.GetDriveType(driveLetter)
            # First cut: only consider removable drives
            if devtype == win32file.DRIVE_REMOVABLE:
                info = getDriveInfo(driveLetter)
                for t in types:
                    if t.isRecorder(info):
                        result.append(info)
                        break
        drivebits >>= 1
    return result


# Module-level globals for caching last discovered logical drives and recorders
_LAST_DEVICES = 0       # Bitmap of logical drives (Z...A)
_LAST_RECORDERS = None  # Tuple of recorder paths (e.g. `["D:\\", "E:\\"]`)


def deviceChanged(recordersOnly: bool, types: Optional[dict] = None, clear: bool = False) -> bool:
    """ Returns `True` if a drive has been connected or disconnected since
        the last call to `deviceChanged()`.
        
        :param recordersOnly: If `False`, any change to the mounted drives
            is reported as a change. If `True`, the mounted drives are checked
            and `True` is only returned if the change occurred to a recorder.
            Checking for recorders only takes marginally more time.
        :param types: A list of known `Recorder` classes to detect. Used if
            `recordersOnly` is `True`.
        :param clear: If `True`, clear the cache of previously-detected
            drives and devices.
    """
    global _LAST_DEVICES, _LAST_RECORDERS
    
    if clear:
        _LAST_DEVICES = 0
        _LAST_RECORDERS = None
    
    newDevices = kernel32.GetLogicalDrives()
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


def getFreeSpace(path: Filename):
    """ Return the free space (in bytes) on a drive.
        
        :param path: The path to the drive to check. Can be a subdirectory.
        :return: The free space on the drive, in bytes.
        :rtype: int
    """
    if isinstance(path, Path):
        filename = str(path)

    free_bytes = ctypes.c_ulonglong(0)
    kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(path), None, None, 
                                 ctypes.pointer(free_bytes))
    return free_bytes.value


def getBlockSize(path: Filename):
    """ Return the bytes per sector and sectors per cluster of a drive.

        :param path: The path to the drive to check. Can be a subdirectory.
        :return: A tuple containing the bytes/sector and sectors/cluster.
    """
    if isinstance(path, Path):
        filename = str(path)

    sectorsPerCluster = ctypes.c_ulonglong(0)
    bytesPerSector = ctypes.c_ulonglong(0)
    kernel32.GetDiskFreeSpaceW(ctypes.c_wchar_p(path), 
                                 ctypes.pointer(sectorsPerCluster),
                                 ctypes.pointer(bytesPerSector),
                                 None, None)
    
    return bytesPerSector.value, sectorsPerCluster.value
