"""
Find an enDAQ MQTT broker.

The simplest way to find an enDAQ MQTT broker is using `findBroker`
"""

import copy
from dataclasses import dataclass, asdict
from fnmatch import fnmatchcase
import inspect
import logging
import re
from threading import RLock, Timer
from time import sleep, time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import warnings
import weakref

from zeroconf import Zeroconf, ServiceBrowser, ServiceInfo, ServiceStateChange

from endaq.device.util import synchronized, levenshtein


logger = logging.getLogger(__name__)

# ===========================================================================
#
# ===========================================================================

# DEFAULT_NAME = "enDAQ Remote Interface._endaq._tcp.local."
DEFAULT_NAME = "Data Collection Box Interface._endaq._tcp.local."
DEFAULT_NAMES = ["enDAQ Remote Interface*._endaq._tcp.local.",
                 "Data Collection Box Interface*._endaq._tcp.local."]
SERVICE_TYPE = "_endaq._tcp.local."

MDNS_FINDERS: Dict[str, "MDNSFinder"] = weakref.WeakValueDictionary()

# ===========================================================================
#
# ===========================================================================


# noinspection deprecation
@dataclass
class MDNSInfo:
    """
    Dataclass for organizing info about mDNS services

    :param name: Root name of mDNS service name, excluding service type
        (e.g., ``name`` from ``name._endaq._tcp.local.``).
    :param serviceType: The mDNS service name name of mDNS name (e.g.,
        ``._endaq._tcp.local.`` from ``name._endaq._tcp.local.``).
    :param host: A list of the service's advertised IP addresses. Generally,
        only the first item is used
    :param port: The advertised service's port number.
    :param server: The advertised service's resolvable server name.
    :param properties: Properties advertised by the mDNS host.
    """
    name: str
    serviceType: str
    host: List[str]
    port: int
    server: str
    properties: Dict[bytes, Optional[bytes]]


    # For backwards compatibility with earlier version that returned brokers as dicts.
    # These will be removed in the future.

    def _asdict(self) -> Dict[str, Any]:
        warnings.warn("mDNS info now returned as an MDNSInfo object; dict methods will be deprecated",
                      DeprecationWarning)
        return asdict(self)

    def __getitem__(self, k):
        return self._asdict()[k]

    def get(self, *args):
        return self._asdict().get(*args)

    def keys(self):
        return self._asdict().keys()

    def values(self):
        return self._asdict().values()

    def items(self):
        return self._asdict().values()


class MDNSFinder:
    """
    Object to handle searching for mDNS hosts. Most of the work is handled
    by Zeroconf in the background.
    """

    # FUTURE: Redo instance memoization in __new__()? Remember __init__() always called.

    def __init__(self,
                 serviceType: str = SERVICE_TYPE,
                 timeout: Union[float, int] = 5.0,
                 keepalive: Union[float, int] = 180.0):
        """
        Object to handle searching for mDNS hosts. Most of the work is handled
        by Zeroconf in the background.

        :param serviceType: The service type to find. Each `MDNSFinder`
            instance scans for a single service type.
        :param timeout: How many seconds to wait while querying for mDNS host
            info before giving up.
        :param keepalive: The time to keep the `MDNSFinder` object running
            between uses.
        """
        self.serviceType = serviceType
        self.timeout = timeout
        self._timeout_ms = int(timeout * 1000)
        self._keepalive = keepalive
        self._callbacks: set[weakref.ReferenceType] = set()

        self._zc = None                        # Holder for Zeroconf object
        self._browser = None                   # Holder for serviceBrowser
        self._found: Dict[str, MDNSInfo] = {}  # Dict of mDNS items indexed by full name
        self._lastReported: List[int] = []

        self._synchronized_lock = RLock()  # Same as used in the `@synchronized` decorator
        self._timer = Timer(keepalive, self.stop)
        self._callbackTimer = Timer(1, lambda x: None)

        self.start_time = 0
        MDNS_FINDERS[serviceType] = self


    def __repr__(self) -> str:
        # __repr__() should never completely fail, so:
        # noinspection broad-exception
        try:
            active = 'active' if self.active else 'inactive'
            return f'<{type(self).__name__} {self.serviceType!r} ({active}) at {hex(id(self))}>'
        except Exception:
            return super().__repr__()


    @property
    def active(self) -> bool:
        """ Is the `MDNSFinder` currently running? """
        try:
            if self._zc is None:
                return False
            return self._zc.started
        except AttributeError:
            return False


    @property
    def keepalive(self) -> Union[float, int, None]:
        return self._keepalive


    @keepalive.setter
    def keepalive(self, lifetime: Union[float, int]):
        self._keepalive = lifetime
        self._resetTimer()


    @synchronized
    def _cleanCallbacks(self):
        for dead in [x for x in self._callbacks if x() is None]:
            self._callbacks.remove(dead)


    @property
    @synchronized
    def callbacks(self) -> tuple[Callable, ...]:
        """ List all active callbacks.
        """
        self._cleanCallbacks()
        return tuple(c() for c in self._callbacks if c() is not None)


    @synchronized
    def addCallback(self, callback: Callable[[List[MDNSInfo]], None]):
        """
        Add a function to be called whenever the mDNS advertising updates
        (e.g., a broker advertisement goes up or comes down). The function
        should take one argument: a list of active brokers as `MDNSInfo`.
        Note: when there are multiple callbacks, the order of execution is
        arbitrary. If a specific sequence is required, implement it in a
        single callback.

        :param callback: The callback function to add.
        """
        self._cleanCallbacks()
        if inspect.ismethod(callback):
            self._callbacks.add(weakref.WeakMethod(callback))
        elif callable(callback):
            self._callbacks.add(weakref.ref(callback))
        else:
            raise TypeError(f'argument should be callable, not {type(callback)}')


    @synchronized
    def removeCallback(self, callback: Callable):
        """ Remove a callback function added with `addCallback()`.

            :param callback: The callback function to remove.
        """
        remove = None
        for c in self._callbacks:
            if c() == callback:
                remove = c
                break
        self._callbacks.remove(remove)


    @synchronized
    def clearCallbacks(self):
        """ Remove all callback functions.
        """
        self._callbackTimer.cancel()
        self._callbacks.clear()


    def _resetTimer(self):
        """ Start/restart the automatic stop timer.
        """
        self._timer.cancel()
        if self._keepalive is not None:
            self._timer = Timer(self._keepalive, self.stop)
            self._timer.name = f'Reset{self._timer.name}'  # for debugging
            self._timer.start()


    def _callback(self):
        """
        Wrapper to execute all the callback functions with an
        up to date list.
        """
        brokers = self.getBrokerList()

        if brokers == self._lastReported:
            return

        for callback in self._callbacks:
            try:
                c = callback()
                if c is not None:
                    # noinspection calling-non-callable
                    c(brokers)
            except Exception as e:
                logger.exception(e)
        self._lastReported = brokers


    def _onServiceStateChange(self,
                              zeroconf: Zeroconf,
                              service_type: str,
                              name: str,
                              state_change: ServiceStateChange):
        """
        Called by Zeroconf serviceBrowser when an mDNS is added, removed,
        or updated. Do not change these parameters or names! They are
        required by Zeroconf.
        """
        # Note: this method explicitly uses the lock typically created/used
        # by the `@synchronized` decorator; `get_service_info()` may take 
        # time, and only the dict access before/after needs to block.

        if state_change == ServiceStateChange.Removed and name in self._found:
            with self._synchronized_lock:
                del self._found[name]
        else:
            info = zeroconf.get_service_info(service_type, name, timeout=self._timeout_ms)
            if info:
                with self._synchronized_lock:
                    self._found[info.name] = parseServiceInfo(info)
            else:
                logger.debug(f"getinfo failed for {name} ({service_type}) ")
                return

        if self._callbacks and not self._callbackTimer.is_alive():
            self._callbackTimer = Timer(1, self._callback)
            self._callbackTimer.name = f'Callback{self._callbackTimer.name}'
            self._callbackTimer.start()


    @synchronized
    def start(self):
        """
        Start searching for the specified mDNS service types.
        """
        self._resetTimer()

        if self.active:
            return

        self._zc = Zeroconf()
        self._browser = ServiceBrowser(
            zc=self._zc,
            type_=[self.serviceType],
            handlers=[self._onServiceStateChange],
        )

        self.start_time = time()


    @synchronized
    def stop(self):
        """
        Close out the search and delete all results.
        """
        self._timer.cancel()
        if self._zc is not None:
            self._browser.cancel()
            self._zc.close()
        self._zc = None
        self._found.clear()


    @synchronized
    def getBrokerDict(self) -> Dict[str, MDNSInfo]:
        """
        Get a dictionary of discovered brokers, keyed by name.

        :returns: A dictionary of the brokers.
        """
        self.start()
        return copy.deepcopy(self._found)


    def getBrokerList(self) -> List[MDNSInfo]:
        """
        Get a list of advertised brokers.

        :returns: list of the brokers
        """
        return sorted(self.getBrokerDict().values(), key=lambda x: x.name)


    @synchronized
    def restart(self, min_lifetime: int = 5):
        """
        Stop and restart the discovery process unless it has already been
        started within min_lifetime seconds

        :param min_lifetime: Don't kill the previous process if it was
            started min_lifetime seconds ago
        """
        if time() - self.start_time < min_lifetime:
            self._resetTimer()
            return

        self.stop()
        self.start()


def splitServiceName(serviceName: str) -> Tuple[str, str]:
    """
    Split a full mDNS name (including service) into the base name and the
    service name. So ``"name._endaq._tcp.local."`` becomes ``"name"`` and
    ``"_endaq._tcp.local."``.
    """
    if m := re.match(r"(.+)\.(.+\._tcp\.local\.)", serviceName):
        return m.groups()
    return serviceName, SERVICE_TYPE


def fullServiceName(service: Union[str, MDNSInfo]) -> str:
    if isinstance(service, str):
        n, t = splitServiceName(service)
        return f"{n}.{t}"
    return f'{service.name}.{service.serviceType}'


def parseServiceInfo(info: ServiceInfo) -> MDNSInfo:
    """
    Parse `zeroconf.ServiceInfo` into an `MDNSInfo` object.
    """
    name, serviceType = splitServiceName(info.name)
    addr = info.parsed_addresses()
    # Some services' properties contain null keys
    props = {k: v for k, v in info.properties.items() if k}
    return MDNSInfo(name=name, serviceType=serviceType,
                    host=addr, port=info.port, server=info.server,
                    properties=props)


def getBroker(name: str = DEFAULT_NAME,
              limit: Union[float, int] = 5,
              scantime: Union[float, int] = 2,
              timeout: Union[float, int] = 5,
              callback: Optional[Callable] = None,
              keepalive: Union[float, int] = 180.0,
              protocol: str = 'mqtt') -> MDNSInfo:
    """
    Find a specific enDAQ-advertised MQTT Broker by name. The closest match
    will be returned.

    :param name: The name of the broker to find.
    :param limit: The maximum number of differences between the given name
        and a broker name to be considered a match. `None` will return
        the first broker discovered.
    :param scantime: The minimum time (in seconds) to scan for brokers. If
        any brokers are discovered in this time, they will be returned.
    :param timeout: The maximum time (in seconds) to scan for brokers, if
        none were found in `scantime`.
    :param callback: A function to call repeatedly while scanning. If the
        callback returns `True`, the wait for a response will be cancelled.
        The callback function should require no arguments.
    :param keepalive: If `True`, keep the mDNS finding object open for
        later use (this can make subsequent discovery faster and more
        accurate).
    :param protocol: The advertised broker's self-reported protocol.
    :returns: A `MDNSInfo` object.
    """
    _, serviceType = splitServiceName(name)
    broker_list = findBrokers(serviceType=serviceType, scantime=scantime,
                              timeout=timeout, callback=callback,
                              keepalive=keepalive, protocol=protocol)
    if not broker_list:
        return None

    fullname = fullServiceName(name)
    broker_list = [(levenshtein(fullServiceName(x.name), fullname), x) for x in broker_list]
    broker = min(broker_list, key=lambda x: x[0])
    if limit is None or broker[0] <= limit:
        return broker[0]
    return None


def findBrokers(*patterns: str,
                serviceType: str = SERVICE_TYPE,
                scantime: Union[float, int] = 2,
                timeout: Union[float, int] = 5,
                callback: Optional[Callable] = None,
                keepalive: Union[float, int] = 180.0,
                protocol: str = 'mqtt') -> List[MDNSInfo]:
    """
    Find enDAQ-advertised MQTT Brokers.

    :param patterns: Zero or more MQTT Broker names (multiple positional
        arguments). Glob-like wildcards may be used (case-sensitive).
        No positional arguments or `None` will return all MQTT brokers.
    :param serviceType: The service type to find.
    :param scantime: The *minimum* time (in seconds) to scan for brokers. If
        any brokers are discovered in this time, they will be returned.
    :param timeout: The *maximum* time (in seconds) to scan for brokers, if
        none were found in `scantime`.
    :param callback: A function to call repeatedly while scanning. If the
        callback returns `True`, the wait for a response will be cancelled.
        The callback function should require no arguments.
    :param keepalive: If `True`, keep the mDNS finding object open for
        later use (this can make subsequent discovery faster and more
        accurate).
    :param protocol: The advertised broker's self-reported protocol.
    :returns: A list of MQTT Brokers.
    """
    scanDeadline = time() + scantime
    deadline = time() + timeout
    broker_list = []
    protocol = bytes(protocol, 'utf-8') if protocol is not None else None

    if serviceType not in MDNS_FINDERS:
        finder = MDNSFinder(serviceType, timeout=timeout, keepalive=keepalive)
    else:
        finder = MDNS_FINDERS[serviceType]

    finder.start()

    while time() < deadline:
        sleep(0.1)

        broker_list = finder.getBrokerList()

        if protocol is not None:
            broker_list = [broker for broker in broker_list
                           if broker.properties.get(b'protocol', b'mqtt') == protocol]

        if patterns and patterns[0]:
            broker_list = [broker for broker in broker_list
                           if any(fnmatchcase(broker.name, p) for p in patterns)]

        if broker_list and time() > scanDeadline:
            break

        if callback and callback():
            break

    return broker_list


if __name__ == "__main__":
    """
    Just print added and removed mDNS items.
    """
    finder = MDNSFinder()
    finder.start()
    hosts = {}
    print(f"Scanning for mDNS Hosts:")
    while True:
        old_hosts = hosts
        hosts = finder.getBrokerDict()
        alive = []
        for host_id in hosts:
            if host_id in old_hosts:
                alive.append(host_id)
            else:
                print(f"Found new host: {host_id} at {hosts[host_id].host}")
        dead = [x for x in old_hosts if x not in alive]
        for host_id in dead:
            print(f"Host removed: {host_id} at {old_hosts[host_id].host}")
