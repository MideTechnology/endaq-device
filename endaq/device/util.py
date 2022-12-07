"""
Some basic utility functions, for internal use.
"""

import errno
import os.path
import pathlib
import shutil
import typing

import logging
logger = logging.getLogger("endaq.device")


def makeBackup(filename: typing.Union[str, pathlib.Path]) -> bool:
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


def restoreBackup(filename: typing.Union[str, pathlib.Path],
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


def cleanProps(el: dict):
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
