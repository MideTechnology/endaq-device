"""
Some basic utility functions, for internal use.
"""

import calendar
import datetime
import errno
import os.path
import pathlib
import shutil
import socket
from threading import get_native_id
from typing import Any, ByteString, Dict, Tuple, Union

import logging
logger = logging.getLogger(__name__)


def makeBackup(filename: Union[str, pathlib.Path]) -> bool:
    """ Create a backup copy of the given file. For use in conjunction with
        `restoreBackup()`.
    """
    try:
        backupFilename = filename + "~"
        if os.path.exists(filename):
            shutil.copy2(filename, backupFilename)
            return True
    except IOError as err:
        logger.error(f'Failed to create backup of {filename} '
                     f'({errno.errorcode.get(err.errno, "?")}: {err.strerror}), ignoring')
    return False


def restoreBackup(filename: Union[str, pathlib.Path],
                  remove: bool = False) -> bool:
    """ Restore a backup copy of a file, overwriting the file. For use in
        conjunction with `makeBackup()`.
    """
    try:
        backupFilename = filename + "~"
        if os.path.exists(backupFilename):
            shutil.copy2(backupFilename, filename)
            if remove:
                os.remove(backupFilename)
            return True
    except IOError as err:
        logger.error(f'Failed to restore backup of {filename} '
                     f'({errno.errorcode.get(err.errno, "?")}: {err.strerror}), ignoring')
    return False


def cleanProps(el: Dict[str, Any]) -> Dict[str, Any]:
    """ Recursively remove unknown elements (``"UnknownElement"`` keys) from
        a dictionary of device properties. The original data may contain
        nested dictionaries and lists. For preparing data dumped from EBML
        for re-encoding.

        Nested dictionaries and lists are deep-copied. Note: the contents of
        `bytearray` objects are not duplicated; the copy of the dictionary
        will reference the same ones as the original.

        :return: A deep copy of the original dictionary, minus unknown
            elements.
    """
    if isinstance(el, list):
        return [cleanProps(x) for x in el]
    elif not isinstance(el, dict):
        return el

    return {k: cleanProps(v) for k, v in el.items() if k != "UnknownElement"}


def dump(data: ByteString, length: int = 8) -> str:
    """ Tool to render `bytes` and `bytearray` values in human-readable hex
        (sets of 2 digits, separated by spaces), for debugging and/or
        logging.

        :param data: The `bytes` or `bytearray` data to render.
        :param length: The maximum number of bytes to render. 0 or `None`
            to render all bytes.
    """
    if not length:
        length = len(data)
    return ' '.join(f'{x:02x}' for x in data[:length])


def time2epoch(t: Union[int, float, datetime.datetime, tuple]) -> int:
    """ Convenient function to convert any of several representations
        of time (`datetime`, timestamps, time struct, etc.) into
        integer UNIX epoch timestamps (UTC).
    """
    if isinstance(t, datetime.datetime):
        return calendar.timegm(t.timetuple())
    elif isinstance(t, tuple):
        return calendar.timegm(t)
    else:
        return int(t)


def splitVersion(rev: int) -> Tuple[int, int, int]:
    """ Split up a version number (HwRev/FwRev) into a three-part tuple.
        New 5+ digit xXYYZZ version numbers are split into (x, y, z).
        3-4 digit xXYY numbers are converted to (x, y, 0).
        Old style 1-2 digit numbers are converted to (1, x, 0).
    """
    if rev > 99:
        split = int(rev / 10000), int((rev % 10000) / 100), int(rev % 100)
        if rev < 10000:
            return split[1], split[2], 0
        return split
    return 1, int(rev), 0


def formatHwRev(rev: int) -> str:
    """ Render an integer HwRev in v<version>r<revision>[BOM] format.
    """
    try:
        major, minor, bom = splitVersion(rev)
        if bom == 0:
            bom = ""
        elif bom < 26:
            bom = chr(bom + 65)
        else:
            bom = chr((bom % 25) + 64) * int((bom // 25 + 1))
        return f"v{int(major)}r{int(minor)}{bom}"
    except TypeError:
        pass
    return str(rev)


def formatFwRev(rev: int) -> str:
    """ Render an integer FwRev in major.minor.micro format.
    """
    try:
        return "{}.{}.{}".format(*splitVersion(rev))
    except TypeError:
        return str(rev)


# noinspection PyDeprecation
def utcfromtimestamp(timestamp: int) -> datetime.datetime:
    """ Convert an Epoch timestamp to a UTC datetime, getting around
        deprecated `datetime.datetime.utcfromtimestamp` needed for
        Python 3.9. To be removed once Python 3.9 is sunsetted.
    """
    try:
        return datetime.datetime.fromtimestamp(timestamp, datetime.UTC)
    except AttributeError:
        return datetime.datetime.utcfromtimestamp(timestamp)


def levenshtein(a: str, b: str) -> int:
    """Calculates the Levenshtein distance between a and b.
    """
    n, m = len(a), len(b)
    if n > m:
        # Make sure n <= m, to use O(min(n,m)) space
        a, b = b, a
        n, m = m, n

    current = range(n + 1)
    for i in range(1, m + 1):
        previous, current = current, [i] + [0] * n
        for j in range(1, n + 1):
            add, delete = previous[j] + 1, current[j - 1] + 1
            change = previous[j - 1]
            if a[j - 1] != b[i - 1]:
                change = change + 1
            current[j] = min(add, delete, change)

    return current[n]


# ===========================================================================
#
# ===========================================================================

def getMyIP() -> str:
    """ Retrieve the computer's IP address (v4).
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


def makeClientID(base: str) -> str:
    """ Generate a unique but readable ID for the MQTT Client. The ID
        combines the name of a parent object, the machine's IP, and the
        thread ID from which the function was called.
    """
    # This is *probably* unique enough.
    return f'{base}_{getMyIP()}_{get_native_id()}'
