"""
Mechanisms for saving device information (e.g., IDE headers or data
retrieved from the device.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
import logging
import os
import sys
from typing import Optional

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

    def __init__(self):
        """
        Base class that abstracts the mechanism behind caching device data
        (info, IDE header, etc.).
        """
        self._cache = defaultdict(dict)
        self._modified = defaultdict(dict)


    @synchronized
    def _get(self, sn: int, base: str) -> Optional[bytes]:
        return self._cache[sn].get(base)


    @synchronized
    def _set(self, sn: int, base: str, data: bytes):
        self._cache[sn][base] = data


    def get(self, sn: int, base: str) -> Optional[bytes]:
        """
        Get the latest cached version device data.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: The cached data, or `None` if no cache exists.
        """
        data = self._get(sn, base)
        if data:
            return data
        return self.revert(sn, base)


    def set(self, sn: int, base: str, data: bytes) -> bool:
        """
        Set the data cache in memory.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :param data: The new header.
        :return: True if the cache was updated with new data.
        """
        old = self._get(sn, base)
        if old == data:
            return False
        self._set(sn, base, data)
        self.setModified(sn, base, True)
        return True


    @synchronized
    def modified(self, sn: int, base: str) -> bool:
        """
        Check if the cached data was modified since last save.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        """
        return self._modified[sn].get(base, False)


    @synchronized
    def setModified(self, sn: int, base: str, modified=True):
        """
        Explicitly set (or clear) the flag indicating a change in a set of
        cached data since last save.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :param modified: The new value.
        """
        self._modified[sn][base] = modified


    # =======================================================================
    #
    # =======================================================================

    @abstractmethod
    def save(self, sn: int, base: str, force=False) -> bool:
        """
        Write the currently cached data.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :param force: If `True`, overwrite the cached header even if it
            has not been changed, updating its cache timestamp.
        """
        raise NotImplementedError()


    @abstractmethod
    def revert(self, sn: int, base: str) -> Optional[bytes]:
        """
        Reload the last saved version of the cached data.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: The cached data, or `None` if no cache exists.
        """
        raise NotImplementedError()


    @abstractmethod
    def getTimestamp(self, sn: int, base: str) -> Optional[float]:
        """
        Get the date/time the cached data was last saved.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: The update's timestamp (UNIX epoch).
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
        super().__init__()


    def _makeFilename(self, sn: int, base: str) -> str:
        """
        Generate a cache filename.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: The full file path and name
        """
        return os.path.realpath(os.path.join(self._cachePath, f'{sn:08d}', base))


    @synchronized
    def save(self, sn: int, base: str, force=False):
        """
        Write the currently cached data.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :param force: If `True`, overwrite the cached header even if it
            has not been changed, updating its cache timestamp.
        """
        if not (force or self.modified(sn, base)):
            return

        data = self._get(sn, base)
        filename = self._makeFilename(sn, base)
        dirname = os.path.dirname(filename)

        try:
            os.makedirs(dirname, exist_ok=True)
        except IOError as err:
            logger.error(f'Error creating cache directory {dirname}: {err!r}')
            return

        try:
            with open(filename, 'wb') as f:
                f.write(data)
            self.setModified(base, sn, False)

        except IOError as err:
            logger.error(f'Error saving cache data {sn:08d}/{base}: {err!r}')


    @synchronized
    def revert(self, sn: int, base: str) -> Optional[bytes]:
        """
        Reload the last saved version of the cached data.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: The cached data, or `None` if no cache exists.
        """
        old = self._get(sn, base)
        filename = self._makeFilename(sn, base)
        
        try:
            with open(filename, 'rb') as f:
                data = f.read()
            self._set(sn, base, data)
            self.setModified(base, sn, old and old != data)
            return data
        except FileNotFoundError:
            return None
        except IOError as err:
            logger.error(f'Error loading file {filename}', exc_info=err)
        

    def getTimestamp(self, sn: int, base: str) -> float:
        """
        Get the date/time the cached data was last saved.

        :param sn: The enDAQ device's serial number.
        :param base: The name of the info, e.g. ``"header"`` or ``"info0"``
        :return: The update's timestamp (UNIX epoch).
        """
        filename = self._makeFilename(sn, base)
        try:
            return os.path.getmtime(filename)
        except FileNotFoundError:
            pass
        except IOError as err:
            logger.error(f'Error getting timestamp of {filename}: {err!r}')
            
        return 0
