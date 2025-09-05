"""
Mechanisms for the Device Manager to load and save cached device information
(e.g., IDE headers or data retrieved from the device).

By default, the caching is done via files in a working directory. The
mechanism is abstracted to make it easy to swap out for another type
of storage (e.g., a database).
"""

import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from glob import glob
import logging
import os
import sys
from time import time
from typing import List, Optional, Tuple

from ..client import synchronized

# Paths for cached data (IDE headers, etc.)
if sys.platform == 'win32':
    CACHE_PATH = os.path.expandvars(r'%APPDATA%\endaq\mqtt_manager')
else:
    CACHE_PATH = os.path.expanduser('~/.endaq/mqtt_manager')

logger = logging.getLogger(__name__)


# ===========================================================================
#
# ===========================================================================

class BaseCache(ABC):
    """
    Base class that abstracts the mechanism behind caching device data
    (info, IDE header, etc.).
    """

    @abstractmethod
    def get(self, sn: int, base: str) -> bytes:
        """
        Get the latest cached version device data.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: The cached data, or an empty bytestring if no cache exists.
        """
        raise NotImplementedError()


    @abstractmethod
    def set(self, sn: int, base: str, data: bytes) -> bool:
        """
        Store device data in the cache.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :param data: The new header.
        :return: True if the cache was updated with new data.
        """
        raise NotImplementedError()


    @abstractmethod
    def clear(self, sn: int, base: str) -> bool:
        """
        Remove data from the cache.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: `True` if the cached existed and its removal was successful.
        """
        raise NotImplementedError()


    @abstractmethod
    def getTimestamp(self, sn: int, base: str) -> float:
        """
        Get the date/time the cached data was last saved.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: The update's timestamp (UNIX epoch), or zero if there is no
            cached data.
        """
        raise NotImplementedError()


    @abstractmethod
    def cleanCache(self,
                   sn: Optional[int] = None,
                   base: Optional[str] = None,
                   retention: float = 24) -> List[Tuple[int, str, Optional[Exception]]]:
        """
        Clear out old cached data.

        :param sn: The enDAQ device's serial number, or `None` for all
            devices.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``,
            or `None` for all cached info.
        :param retention: The cached file retention period. Files not
            modified in `retention` hours will be removed.
        :return: A list of tuples: serial number, base, and failure. Failure
            will be `None` if successful, an exception if not.
        """
        raise NotImplementedError()


# ===========================================================================
#
# ===========================================================================

class FileCache(BaseCache):
    """
    Class that implements a file-based mechanism for reading/writing cached
    device data (info, IDE header, etc.).
    """

    def __init__(self, path: str = CACHE_PATH):
        """
        Class that implements a file-based mechanism for reading/writing
        cached device data (info, IDE header, etc.).

        :param path: The root directory of the cached data. Note that the
            default varies by platforn.
        """
        self._cachePath = path
        self._locks = defaultdict(threading.RLock)
        super().__init__()


    def _makeFilename(self, sn: int, base: str) -> str:
        """
        Generate a cache filename.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: The full file path and name
        """
        try:
            sn = f'{sn:08d}'
        except (TypeError, ValueError):
            sn = str(sn)
        return os.path.realpath(os.path.join(self._cachePath, sn, f'{base}.cache'))


    def get(self, sn: int, base: str) -> bytes:
        """
        Retrieve cached data.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: The cached data, or `None` if no cache exists.
        """
        filename = self._makeFilename(sn, base)

        with self._locks[filename]:
            try:
                with open(filename, 'rb') as f:
                    data = f.read()
                return data
            except FileNotFoundError:
                pass
            except IOError as err:
                logger.error(f'Error loading file {filename}', exc_info=err)

            return b''


    def set(self, sn: int, base: str, data: bytes) -> bool:
        """
        Write data to the cache.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :param data: The new header.
        :return: `True` if the cache was updated with new data.
        """
        filename = self._makeFilename(sn, base)

        with self._locks[filename]:
            dirname = os.path.dirname(filename)
            try:
                os.makedirs(dirname, exist_ok=True)
            except IOError as err:
                logger.error(f'Error creating cache directory {dirname}: {err!r}')
                return False

            try:
                with open(filename, 'wb') as f:
                    f.write(data)
                return True

            except IOError as err:
                logger.error(f'Error saving cache data {filename}: {err!r}')
                return False


    def getTimestamp(self, sn: int, base: str) -> float:
        """
        Get the date/time the cached data was last saved.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: The update's timestamp (UNIX epoch), or zero if there is no
            cached data.
        """
        filename = self._makeFilename(sn, base)

        with self._locks[filename]:
            try:
                return os.path.getmtime(filename)
            except FileNotFoundError:
                pass
            except IOError as err:
                logger.error(f'Error getting timestamp of {filename}: {err!r}')

            return 0


    def clear(self, sn: int, base: str) -> bool:
        """
        Remove data from the cache.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: `True` if the cached existed and its removal was successful.
        """
        filename = self._makeFilename(sn, base)

        with self._locks[filename]:
            try:
                os.remove(filename)
                return True
            except FileNotFoundError:
                return False
            except IOError as err:
                logger.error(f'Error removing cached file {filename}: {err!r}')
                return False


    @synchronized
    def cleanCache(self,
                   sn: Optional[int] = None,
                   base: Optional[str] = None,
                   retention: float = 24) -> List[Tuple[int, str, Optional[Exception]]]:
        """
        Clear out old cached data.

        :param sn: The enDAQ device's serial number, or `None` for all
            devices.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``,
            or `None` for all cached info.
        :param retention: The cached file retention period. Files not
            modified in `retention` hours will be removed.
        :return: A list of tuples: serial number, base, and failure. Failure
            will be `None` if successful, an exception if not.
        """
        limit = retention * 60 * 60
        cleared = []

        sn = sn or '*'
        base = base or '*'

        for filename in glob(self._makeFilename(sn, base)):
            dirname, b = os.path.split(filename)
            s = os.path.basename(dirname)
            b = os.path.splitext(b)[0]

            try:
                s = int(s)
            except (TypeError, ValueError):
                pass

            try:
                if time() - os.path.getmtime(filename) > limit:
                    os.remove(filename)
                    cleared.append((s, b, None))
            except (IOError, OSError) as err:
                cleared.append((s, b, err))

        return cleared
