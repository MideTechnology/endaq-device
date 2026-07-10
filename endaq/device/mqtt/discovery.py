"""
Find an enDAQ MQTT broker.
"""

from fnmatch import fnmatchcase
import re
from time import sleep, time
from typing import Any, Callable, Dict, List, Optional, Tuple
from threading import Lock
from dataclasses import dataclass
import copy

from zeroconf import Zeroconf, ServiceBrowser, ServiceInfo, ServiceStateChange

from ..util import levenshtein

# ===========================================================================
#
# ===========================================================================

# DEFAULT_NAME = "enDAQ Remote Interface._endaq._tcp.local."
DEFAULT_NAME = "Data Collection Box Interface._endaq._tcp.local."
DEFAULT_NAMES = ["enDAQ Remote Interface*._endaq._tcp.local.",
                 "Data Collection Box Interface*._endaq._tcp.local."]
SERVICE_TYPE = "_endaq._tcp.local."
MDNS_FINDERS: list["MDNSFinder"] = []

# ===========================================================================
#
# ===========================================================================

@dataclass
class MDNSInfo:
    """
    Dataclass for organizing info about mDNS services
    :param name: Root name of mDNS name, so 'name._endaq._tcp.local.' becomes 'name'
    :param serviceType: Service name of mDNS name, so 'name._endaq._tcp.local.' becomes '_endaq._tcp.local.'
    :param host: list of IP addresses for mDNS advertiser. Generally only the first item is used
    :param port: port number for mDNS advertiser
    :param properties: Properties advertised by the mDNS host
    """
    name: str
    serviceType: str
    host: list[str]
    port: int
    properties: dict[bytes, Optional[bytes]]


class MDNSFinder:
    def __init__(self, *patterns, timeout:float=5.0):
        """
        Object to handle searching for mDNS hosts. Most of the work is handled by Zeroconf in the background
        :param patterns: Zero or more MQTT Broker names (multiple positional
            arguments). Glob-like wildcards may be used (case-sensitive).
            `None` will return all MQTT brokers.
        :param timeout: How many seconds to wait while querying for mDNS host info before giving up
        """
        self._zc = None                         # Holder for Zeroconf object
        self.browser = None                     # Holder for serviceBrowser
        self.lock = Lock()                      # Lock to manage access of mDNS list, which is shared between threads
        self._mdns: dict[str, MDNSInfo] = {}    # Dict of mDNS items indexed by full name. Don't access this without the lock!!!
        #TODO: Clarify the intent here, it looks like patterns=None provides the default, but patterns=[None] provides all results
        if not patterns:
            patterns = DEFAULT_NAMES[:]
        elif patterns[0] is None:
            patterns = None
        else:
            # Add service name if the name doesn't have one.
            patterns = list(patterns)
            for i, n in enumerate(patterns):
                patterns[i] = '{}.{}'.format(*splitServiceName(n))
        self._patterns: Optional[list[str]] = patterns       # TODO: Validate Patterns
        self._timeout_ms = int(timeout * 1000)
        self.start_time = 0

    def _onServiceStateChange(self, zeroconf: Zeroconf,
                              service_type: str,
                              name: str,
                              state_change: ServiceStateChange):
        """
        Called by Zeroconf serviceBrowser when an mDNS is added, removed, or updated
        Do not change these parameters or names! They are required by Zeroconf
        """
        if state_change == ServiceStateChange.Removed:
            with self.lock:
                if name in self._mdns:
                    del self._mdns[name]
            return
        info = zeroconf.get_service_info(service_type, name, timeout=self._timeout_ms)
        if not info:
            # TODO: Log this
            print(f"getinfo failed for {name} ({service_type}) ")
            return
        with self.lock:
            if not self._patterns or any(fnmatchcase(info.name, p) for p in self._patterns):
                self._mdns[info.name]=parseServiceInfo(info)

    def start(self):
        """
        Start searching for the specified mDNS types
        """
        if self._zc is not None:
            return
        self._zc = Zeroconf()
        with self.lock:     # Locking is not really needed here, just being extra safe
            if not self._patterns:
                services = [SERVICE_TYPE]
            else:
                services = [splitServiceName(n)[1] for n in self._patterns]
        self.browser = ServiceBrowser(
            zc=self._zc,
            type_=services,
            handlers=[self._onServiceStateChange],
        )
        self.start_time = time()

    def stop(self):
        """
        Close out the search and delete all results
        """
        if self._zc is not None:
            self.browser.cancel()
            self._zc.close()
        self._zc = None
        with self.lock:
            self._mdns = {}

    def getBrokerDict(self) -> tuple[dict[str, MDNSInfo], list[str]]:
        """
        Copy the dict of brokers and get a separate list of their names
        :returns dict of the brokers and a sorted list of the keys:
        """
        with self.lock:
            # Removing the Levenshtein distance sorting, it looked like we were sorting here, then re-sorting in the broker select
            brokers = copy.deepcopy(self._mdns)
        # TODO: Consider storing names separately and keeping it sorted if we're using this function a lot
        names = sorted(brokers.keys())
        return brokers, names

    def getBrokerList(self) -> list[MDNSInfo]:
        """
        Copy the list of brokers
        :returns list of the brokers:
        """
        brokers = []
        with self.lock:
            for k, v in self._mdns.items():
                brokers.append(copy.deepcopy(v))
        return brokers

    def patternsMatch(self, *patterns) -> bool:
        """
        See if the specified patterns match what this broker is using
        """
        with self.lock:
            if self._patterns is None and patterns is None:
                return True
            my_patterns = set(self._patterns)
        return my_patterns == set(patterns)

    def restart(self, min_lifetime: int=5):
        """
        Stop and restart the discovery process unless it has already been started within min_lifetime seconds
        :param min_lifetime: Don't kill the previous process if it was started min_lifetime seconds ago
        """
        if time()-self.start_time < min_lifetime:
            return
        self.stop()
        self.start()


def splitServiceName(serviceName: str) -> Tuple[str, str]:
    """
    Split a full mDNS name (including service) into the base name and the
    service name. So 'name._endaq._tcp.local.' becomes 'name' and '_endaq._tcp.local.'
    """
    if m := re.match(r"(.+)\.(.+\._tcp\.local\.)", serviceName):
        return m.groups()
    return serviceName, SERVICE_TYPE


def parseServiceInfo(info: ServiceInfo) -> MDNSInfo:
    """
    Parse `zeroconf.ServiceInfo` into a dictionary (for use elsewhere as
    keyword arguments). Resulting dictionary contains items `"name"`
    (string), `"host"` (list of addresses as strings, IPv4 and IPV6 if
    available), `"port"` (int), and `"properties"` (dictionary, provided
    by the service).
    """
    name, serviceType = splitServiceName(info.name)
    addr = info.parsed_addresses()
    # Some services' properties contain null keys
    props = {k: v for k, v in info.properties.items() if k}
    return MDNSInfo(name=name, serviceType=serviceType,
                    host=addr, port=info.port, properties=props)


def getBroker(name: str = DEFAULT_NAME,
              timeout: float = 5) -> MDNSInfo:
    """
    Find a specific enDAQ-advertised MQTT Broker. In the best case, this may
    be marginally faster than `findBrokers()` when looking for a specific
    broker.

    :param name: The name of the broker.
    :param timeout: The timeout, in seconds.
    :return: A dictionary of broker information.
    """
    raise NotImplementedError("Use findBroker, or rewrite this to use MDNSFinder")


def findBrokers(*patterns: str,
                scantime: float = 2,
                timeout: float = 5,
                callback: Optional[Callable] = None, persistent: bool=False) -> List[MDNSInfo]:
    """
    Find enDAQ-advertised MQTT Brokers.

    :param patterns: Zero or more MQTT Broker names (multiple positional
        arguments). Glob-like wildcards may be used (case-sensitive).
        `None` will return all MQTT brokers.
    :param scantime: The minimum time (in seconds) to scan for brokers. If
        any brokers are discovered in this time, they will be returned.
    :param timeout: The maximum time (in seconds) to scan for brokers, if
        none were found in `scantime`.
    :param callback: A function to call repeatedly while scanning. If the
        callback returns `True`, the wait for a response will be cancelled.
        The callback function should require no arguments.
    :return: A list of MQTT Brokers.
    """
    finder = None
    deadline = 0
    scanDeadline = time() + scantime
    keep_open = False
    for broker in MDNS_FINDERS:
        if broker.patternsMatch(patterns):
            finder = broker
            keep_open = True
            break
    if finder is None:
        finder = MDNSFinder(*patterns, timeout=timeout)
        if persistent:
            MDNS_FINDERS.append(finder)
            keep_open = True
        finder.start()
        deadline = time() + timeout


    while time() < deadline:
        if callback and callback():
            break
        if finder.getBrokerList() and time() > scanDeadline:
            break
        sleep(0.1)
    broker_list = finder.getBrokerList()
    if not keep_open:
        finder.stop()
    return broker_list

if __name__ == "__main__":
    """
    Just print added and removed mDNS items.
    """
    finder = MDNSFinder(None)
    finder.start()
    hosts = {}
    print(f"Scanning for mDNS Hosts:")
    while True:
        old_hosts = hosts
        hosts, _ = finder.getBrokerDict()
        alive = []
        for host_id in hosts:
            if host_id in old_hosts:
                alive.append(host_id)
            else:
                print(f"Found new host: {host_id} at {hosts[host_id].host}")
        dead = [x for x in old_hosts if x not in alive]
        for host_id in dead:
            print(f"Host removed: {host_id} at {old_hosts[host_id].host}")
