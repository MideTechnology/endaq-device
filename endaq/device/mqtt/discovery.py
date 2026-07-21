"""
Find an enDAQ MQTT broker.
"""

import copy
from dataclasses import dataclass
from fnmatch import fnmatchcase
import logging
import re
from time import sleep, time
from typing import Callable, Dict, List, Optional, Tuple

from zeroconf import Zeroconf, ServiceBrowser, ServiceInfo, ServiceStateChange

from endaq.device.util import synchronized


logger = logging.getLogger(__name__)

# ===========================================================================
#
# ===========================================================================

# DEFAULT_NAME = "enDAQ Remote Interface._endaq._tcp.local."
DEFAULT_NAME = "Data Collection Box Interface._endaq._tcp.local."
DEFAULT_NAMES = ["enDAQ Remote Interface*._endaq._tcp.local.",
                 "Data Collection Box Interface*._endaq._tcp.local."]
SERVICE_TYPE = "_endaq._tcp.local."
MDNS_FINDERS: List["MDNSFinder"] = []

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
    host: List[str]
    port: int
    properties: Dict[bytes, Optional[bytes]]


    def __getitem__(self, k):
        # For backwards compatibility with earlier version that got brokers as dicts
        return self.__dict__[k]


class MDNSFinder:
    def __init__(self, *patterns, timeout: float = 5.0):
        """
        Object to handle searching for mDNS hosts. Most of the work is handled by Zeroconf in the background
        :param patterns: Zero or more MQTT Broker names (multiple positional
            arguments). Glob-like wildcards may be used (case-sensitive).
            `None` will return all MQTT brokers.
        :param timeout: How many seconds to wait while querying for mDNS host info before giving up
        """
        self._zc = None                         # Holder for Zeroconf object
        self.browser = None                     # Holder for serviceBrowser
        self._mdns: Dict[str, MDNSInfo] = {}    # Dict of mDNS items indexed by full name

        # `*patterns` will always be a tuple w/ 0 or more items (the positional args).
        if not patterns:
            patterns = DEFAULT_NAMES[:]
        elif patterns[0] is None:
            patterns = None
        else:
            # Add service name if the name doesn't have one.
            patterns = list(patterns)
            for i, n in enumerate(patterns):
                patterns[i] = '{}.{}'.format(*splitServiceName(n))

        self._patterns: Optional[List[str]] = patterns       # TODO: Validate Patterns
        self._timeout_ms = int(timeout * 1000)
        self.start_time = 0


    @synchronized
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
        if state_change == ServiceStateChange.Removed and name in self._mdns:
            del self._mdns[name]
            return

        info = zeroconf.get_service_info(service_type, name, timeout=self._timeout_ms)
        if not info:
            logger.debug(f"getinfo failed for {name} ({service_type}) ")
            return

        if not self._patterns or any(fnmatchcase(info.name, p) for p in self._patterns):
            self._mdns[info.name] = parseServiceInfo(info)


    @synchronized
    def start(self):
        """
        Start searching for the specified mDNS service types.
        """
        if self._zc is not None:
            return
        self._zc = Zeroconf()
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


    @synchronized
    def stop(self):
        """
        Close out the search and delete all results.
        """
        if self._zc is not None:
            self.browser.cancel()
            self._zc.close()
        self._zc = None
        self._mdns.clear()


    @synchronized
    def getBrokerDict(self) -> Dict[str, MDNSInfo]:
        """
        Copy the dict of brokers and get a separate list of their names

        :returns: A dictionary of the brokers.
        """
        # Removing the Levenshtein distance sorting, it looked like we were sorting here,
        # then re-sorting in the broker select
        return copy.deepcopy(self._mdns)


    def getBrokerList(self) -> List[MDNSInfo]:
        """
        Copy the list of brokers
        :returns: list of the brokers:
        """
        return list(self.getBrokerDict().values())


    @synchronized
    def patternsMatch(self, *patterns) -> bool:
        """
        See if the specified patterns match what this broker is using.
        """
        if self._patterns is None:
            return True
        return set(self._patterns) == set(patterns)


    @synchronized
    def restart(self, min_lifetime: int = 5):
        """
        Stop and restart the discovery process unless it has already been
        started within min_lifetime seconds

        :param min_lifetime: Don't kill the previous process if it was
            started min_lifetime seconds ago
        """
        if time() - self.start_time < min_lifetime:
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


def parseServiceInfo(info: ServiceInfo) -> MDNSInfo:
    """
    Parse `zeroconf.ServiceInfo` into an `MDNSInfo` object.
    """
    name, serviceType = splitServiceName(info.name)
    addr = info.parsed_addresses()
    # Some services' properties contain null keys
    props = {k: v for k, v in info.properties.items() if k}
    return MDNSInfo(name=name, serviceType=serviceType,
                    host=addr, port=info.port, properties=props)


# noinspection PyUnusedLocal
def getBroker(name: str = DEFAULT_NAME,
              timeout: float = 5) -> MDNSInfo:
    """
    Find a specific enDAQ-advertised MQTT Broker.

    :param name: The name of the broker.
    :param timeout: The timeout, in seconds.
    :returns: A dictionary of broker information.
    """
    raise NotImplementedError("Use findBroker, or rewrite this to use MDNSFinder")


def findBrokers(*patterns: str,
                scantime: float = 2,
                timeout: float = 5,
                callback: Optional[Callable] = None,
                persistent: bool = False) -> List[MDNSInfo]:
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
    :param persistent: If `True`, keep the mDNS finding object open for
        later use (this can make subsequent discovery faster and more
        accurate).
    :returns: A list of MQTT Brokers.
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
