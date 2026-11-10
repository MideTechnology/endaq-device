"""
Some basic utility functions, for internal use.
"""

import base64
import calendar
import datetime
import errno
import ipaddress
from functools import wraps
import os.path
import pathlib
import re
import shutil
from threading import get_native_id, RLock
from time import sleep, time
from typing import Any, ByteString, Callable, Dict, List, Optional, Tuple, Union
import socket

import ifaddr

from .response_codes import CommandResponseCode
from .exceptions import DeviceError

import logging
logger = logging.getLogger(__name__)


def makeBackup(filename: Union[str, pathlib.Path]) -> bool:
    """ Create a backup copy of the given file. For use in conjunction with
        `restoreBackup()`.
    """
    try:
        backupFilename = f"{filename}~"
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
        backupFilename = f"{filename}~"
        if os.path.exists(backupFilename):
            shutil.copy2(backupFilename, filename)
            if remove:
                os.remove(backupFilename)
            return True
    except IOError as err:
        logger.error(f'Failed to restore backup of {filename} '
                     f'({errno.errorcode.get(err.errno, "?")}: {err.strerror}), ignoring')
    return False


def cleanProps(el: Union[Dict[str, Any], List[dict]]) -> Dict[str, Any]:
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

    return {k: cleanProps(v) for k, v in el.items() if not k.startswith("UnknownElement")}


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

def getMyIP(iface: Optional[str] = None,
            timeout: Optional[int] = 3,
            default: str = '127.0.0.1') -> str:
    """ Retrieve the computer's IP address (v4).

        :param iface: The name of a specific network interface/adapter to
            use. If `iface` is a regular expression, the first match will
            be used (e.g., ``"wlan0|mlan0"`` will return the IP of ``wlan0``
            if both are connected).
        :param timeout: The amount of time, in seconds, to wait for the
            specified `iface` to become available (if not immediately
            present). If `None`, wait indefinitely. Only applicable when
            `iface` is specified.
        :param default: The default network interface to use if none
            could be found.
    """
    # FUTURE: Multiple interfaces/IPs and/or IPv6

    # Find a specific interface/adapter
    if iface:
        timeout = float('inf') if timeout is None else timeout
        deadline = time() + timeout
        regex = re.compile(iface)

        while True:
            for adapter in ifaddr.get_adapters():
                if not adapter.ips:
                    continue
                for ip in adapter.ips:
                    if regex.match(ip.nice_name):
                        # Get IPv4 address (IPv6 is a tuple)
                        if isinstance(ip.ip, str):
                            return ip.ip
            if time() >= deadline:
                logger.debug(f'Could not find network interface {iface!r}, '
                             "attempting to get active interface's IP")
                break
            sleep(.5)

    # Get the primary interface's IP
    try:
        # More accurate, but may fail in some conditions
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except (socket.error, OSError):
        try:
            # Alternate method (safer, but may return loopback on some systems)
            name = socket.gethostname()
            return socket.gethostbyname(name)
        except (socket.error, OSError) as err:
            if default is None:
                raise
            logger.error(f"Could not get IP, defaulting to {default} ({err!r})")
            return default


def getMyIPs(iface: Optional[str] = None,
             ipv4: bool = True,
             ipv6: bool = True,
             linkLocal: bool = True) -> List[str]:
    """ Retrieve all of the computer's non-loopback IP addresses, for
        advertising a service (e.g., via mDNS) on both IPv4 and IPv6.
        Scope IDs are not included in IPv6 link-local addresses, since
        mDNS address records do not carry them; receivers attach their
        own scope.

        :param iface: The name of a specific network interface/adapter to
            use, or a regular expression matching one or more names. All
            interfaces are used if `None`.
        :param ipv4: If `True`, include IPv4 addresses.
        :param ipv6: If `True`, include IPv6 addresses.
        :param linkLocal: If `True`, include IPv6 link-local (``fe80::/10``)
            addresses.
        :return: A list of addresses, IPv4 first (if any).
    """
    regex = re.compile(iface) if iface else None
    v4, v6 = [], []

    for adapter in ifaddr.get_adapters():
        if regex and not regex.match(adapter.nice_name):
            continue
        for ip in adapter.ips:
            if isinstance(ip.ip, str):
                addr = ipaddress.ip_address(ip.ip)
                if ipv4 and not addr.is_loopback and str(addr) not in v4:
                    v4.append(str(addr))
            else:
                # ifaddr reports IPv6 as (address, flowinfo, scope_id)
                addr = ipaddress.ip_address(ip.ip[0].split('%')[0])
                if (not ipv6 or addr.is_loopback
                        or (addr.is_link_local and not linkLocal)
                        or str(addr) in v6):
                    continue
                v6.append(str(addr))

    # Globally routable IPv6 before link-local
    v6.sort(key=lambda a: ipaddress.ip_address(a).is_link_local)
    return v4 + v6


def isLocalhost(host: Optional[str]) -> bool:
    """ Is `host` empty, ``localhost``, or a loopback IP literal (v4 or v6)?
    """
    if not host or host.lower() == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host.strip('[]').split('%')[0]).is_loopback
    except ValueError:
        return False


def formatHost(host: str) -> str:
    """ Format a hostname or IP literal for use in the authority part of a
        URL (RFC 3986/6874). IPv6 literals are enclosed in brackets, and
        a zone ID (e.g., the ``eth0`` or ``2`` in ``fe80::1%eth0``) is
        percent-encoded as ``%25``. Hostnames and IPv4 addresses are
        returned unchanged.

        :param host: A hostname, IPv4 address, or IPv6 address (with or
            without brackets and/or a zone ID).
        :return: The host, formatted for use in a URL.
    """
    bare = host.strip('[]')
    addr, _, zone = bare.partition('%')
    if zone.startswith('25') and host.startswith('['):
        # Already URL-encoded zone ID
        zone = zone[2:]
    try:
        if ipaddress.ip_address(addr).version != 6:
            return addr
    except ValueError:
        return host
    if zone.isdigit():
        # Numeric zone IDs (interface indexes, as reported by zeroconf) are
        # mangled by `urllib3`'s percent-decoding ('%252' -> '%2'); use the
        # interface name instead.
        try:
            zone = socket.if_indextoname(int(zone))
        except (OSError, AttributeError) as err:
            logger.debug(f'Could not get name of interface {zone}: {err!r}')
    return f'[{addr}%25{zone}]' if zone else f'[{addr}]'


def orderAddresses(addresses: List[str],
                   prefer: Optional[str] = None) -> List[str]:
    """ Sort a list of IP address strings by address family.

        :param addresses: The addresses (e.g., `MDNSInfo.host`).
        :param prefer: ``"ipv6"`` to put IPv6 first (globally routable
            before link-local), ``"ipv4"`` to put IPv4 first, or `None`
            to keep the original order.
        :return: A new, sorted list.
    """
    if not prefer:
        return list(addresses)
    want6 = prefer.lower() in ('ipv6', 'v6', '6')

    def key(a: str):
        try:
            ip = ipaddress.ip_address(a.split('%')[0])
        except ValueError:
            return 2, False  # Hostnames last
        return (0 if (ip.version == 6) == want6 else 1), ip.is_link_local

    return sorted(addresses, key=key)


def makeClientID(base: str) -> str:
    """ Generate a unique but readable ID for the MQTT Client. The ID
        combines the name of a parent object, the machine's IP, and the
        thread ID from which the function was called.
    """
    # This is *probably* unique enough.
    return f'{base}_{getMyIP()}_{get_native_id()}'


def waitfor(func: Callable,
            timeout: float,
            interval: float = 0.125,
            callback: Optional[Callable] = None) -> bool:
    """ Helper to wait for a condition to be met.

        :param func: A function to call that checks the condition. It
            should require no arguments and return `True` if the
            condition is met. It will be called at least once.
        :param timeout: Time (in seconds) to wait for the condition
            to be met. 0 will return immediately; `None` or -1 will wait
            indefinitely.
        :param interval: Time (in seconds) between checks.
        :param callback: A function to call each response-checking
            cycle. If the callback returns `True`, the wait for a
            response will be cancelled. The callback function should
            require no arguments.
    """
    if timeout == 0:
        return func()

    timeout = -1 if timeout is None else timeout
    deadline = time() + timeout

    while timeout < 0 or time() < deadline:
        if callback is not None and callback():
            return False
        if func():
            return True
        sleep(interval)

    raise TimeoutError


def decodeAttr(data: Dict[str, Any], obj: Any):
    """ Decode an EBML `Attribute` element (defined in several enDAQ/Mide
        schemata) and update an object's `attributes` attribute. Used to
        process some special-case metadata.
    """
    name = data.pop('AttributeName')

    attrs = getattr(obj, 'attributes', None)
    if attrs is None:
        attrs = obj.attributes = {}

    for k, v in data.items():
        if k.endswith('Attribute'):
            try:
                attrs[name].append(v)
            except KeyError:
                attrs[name] = [v]


# ===========================================================================
# Decorators
# ===========================================================================

def synchronized(method):
    """ Decorator for making methods use a lock, modeled after the one in
        Java. It uses `threading.RLock`; synchronized methods called from
        the same thread that has claimed the lock are not blocked.
    """
    @wraps(method)
    def wrapped(instance, *args, **kwargs):
        try:
            lock = instance._synchronized_lock
        except AttributeError:
            lock = instance._synchronized_lock = RLock()
        with lock:
            return method(instance, *args, **kwargs)
    return wrapped


def device_synchronized(method):
    """ A specialized version of the `synchronized` decorator for objects
        that have a `device` attribute referring to a `Recorder` instance.
    """
    @wraps(method)
    def wrapped(instance, *args, **kwargs):
        try:
            lock = instance.device._synchronized_lock
        except AttributeError:
            if not instance.device:
                # Edge case: object's `device` not assigned (e.g., a
                # `CommandInterface` that was explicitly instantiated)
                # Call without lock.
                return method(instance, *args, **kwargs)
            else:
                lock = instance.device._synchronized_lock = RLock()

        with lock:
            return method(instance, *args, **kwargs)

    return wrapped


def _synchronized(method):
    """ A version of the `synchronized` decorator that does some logging,
        for debugging use.
    """
    @wraps(method)
    def wrapped(instance, *args, **kwargs):
        try:
            lock = instance._synchronized_lock
        except AttributeError:
            lock = instance._synchronized_lock = RLock()
        with lock:
            # Don't log the `in_waiting` property checks (too many calls)
            if 'waiting' not in str(method):
                logger.debug(f'>>> calling synchronized method {method} (thread {get_native_id()})')
            try:
                return method(instance, *args, **kwargs)
            finally:
                if 'waiting' not in str(method):
                    logger.debug(f'<<< exiting synchronized method {method} (thread {get_native_id()})')
    return wrapped


def _device_synchronized(method):
    """ A version of the `device_synchronized` decorator that does some logging,
        for debugging use.
    """
    @wraps(method)
    def wrapped(instance, *args, **kwargs):
        try:
            lock = instance.device._synchronized_lock
        except AttributeError:
            if hasattr(instance, 'device'):
                lock = instance.device._synchronized_lock = RLock()
            else:
                # Edge case: object's `device` not assigned.
                # Ignore, use dummy lock.
                lock = RLock()
        with lock:
            # Don't log the `in_waiting` property checks (too many calls)
            if 'waiting' not in str(method):
                logger.debug(f'>>> calling synchronized method {method} (thread {get_native_id()})')
            try:
                return method(instance, *args, **kwargs)
            finally:
                if 'waiting' not in str(method):
                    logger.debug(f'<<< exiting synchronized method {method} (thread {get_native_id()})')
    return wrapped


def info_lock_required(func: Callable,
                       what: str = 'Function/method call') -> Optional[bytes]:
    """ Convenience function for getting/setting info requiring the device's
        Lock ID match the host's. It turns ERR_BAD_LOCK_ID errors into a
        more useful message, since .

        :param func: The function to be called, e.g., a `functools.partial`
            that calls `CommandInterface._getInfo()` or
            `CommandInterface._setInfo()` with the required parameters.
        :param what: The name or short description of the function called.
    """
    try:
        return func()
    except DeviceError as err:
        if err.errno == CommandResponseCode.ERR_BAD_LOCK_ID:
            err.args = (err.args[0],
                        f'{what} requires a matching lock ID '
                        'set with Recorder.command.setLockID()')
        raise


# ===========================================================================
# Safer JSON serialization
# Note: This may get moved into `ebmlite`
# ===========================================================================

def decodeDict(value: Union[Dict[str, Any], list]) -> None:
    """ Convert `bytearray`/`bytes` values in a dict/list escaped by
        `encodeDict()` back to their original form. The original
        dict/list is modified in place.
    """
    if isinstance(value, list):
        iterator = enumerate(value)
    elif isinstance(value, dict):
        iterator = value.items()
    else:
        raise ValueError(f'cannot iterate {type(value)}')

    for i, v in iterator:
        if isinstance(v, str) and v.startswith('base64:'):
            value[i] = base64.b64decode(v[7:])
        elif isinstance(v, (dict, list)):
            decodeDict(v)


def encodeDict(value: Union[Dict[str, Any], list]) -> None:
    """ Convert all strings in a list/dict starting with ``"base64"`` into
        `bytearray`/`bytes` values. The original dict/list is modified in
        place.
    """
    if isinstance(value, list):
        iterator = enumerate(value)
    elif isinstance(value, dict):
        iterator = value.items()
    else:
        raise ValueError(f'cannot iterate {type(value)}')

    for i, v in iterator:
        if isinstance(v, (bytes, bytearray)):
            value[i] = 'base64:' + str(base64.b64encode(v), 'utf8')
        elif isinstance(v, (dict, list)):
            encodeDict(v)
