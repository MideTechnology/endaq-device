"""
Find an enDAQ MQTT broker.
"""

from fnmatch import fnmatchcase
import re
from time import sleep, time
from typing import Any, Callable, Dict, List, Optional, Tuple
from threading import Lock
from dataclasses import dataclass

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
mdns_finders: list["MDNSFinder"] = []

# ===========================================================================
#
# ===========================================================================

@dataclass
class MDNSInfo:
    name: str
    serviceType: str
    host: str
    port: int
    properties: dict[bytes, bytes | None]


class MDNSFinder:
    def __init__(self, patterns: Optional[list[str]], timeout=5):
        self._zc = None
        self.browser = None
        self.lock = Lock()
        self._mdns_list: list[MDNSInfo] = []
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
        self._patterns: list[str] | None = patterns       # TODO: Validate Patterns
        self._timeout_ms = timeout * 1000

    def _on_service_state_change(self, zeroconf: Zeroconf,
                                service_type: str,
                                name: str,
                                state_change: ServiceStateChange):
        print(f"Called {name} ({service_type}), {state_change}")
        if state_change == ServiceStateChange.Removed:
            with self.lock:
                if name in self._mdns_list:
                    self._mdns_list.remove(name)
            return
        info = zeroconf.get_service_info(service_type, name, timeout=self._timeout_ms)
        if not info:
            print(f"getinfo failed for {name} ({service_type}) ")
            return
        with self.lock:
            if not self._patterns or any(fnmatchcase(info.name, p) for p in self._patterns):
                if info.name not in self._mdns_list:
                    self._mdns_list.append(parseServiceInfo(info))

    def start(self):
        if self._zc is not None:
            return
        self._zc = Zeroconf()
        with self.lock:     # Locking is not really needed here, just being extra safe
            if not self._patterns:
                services = [SERVICE_TYPE]
            else:
                services = [splitServiceName(n)[1] for n in self._patterns]
        print(f"Starting discovery with {services=}")
        self.browser = ServiceBrowser(
            zc=self._zc,
            type_=services,
            handlers=[self._on_service_state_change],
        )

    def close(self):
        if self._zc is not None:
            self.browser.cancel()
            self._zc.close()
        self._zc = None
        with self.lock:
            self._mdns_list = []

    def get_brokers(self) -> list[MDNSInfo]:
        with self.lock:
            if self._patterns and len(self._mdns_list) > 1:
                # Sort by similarity to patterns
                self._mdns_list.sort(key=lambda x: min(levenshtein(x.name, p)
                                                   for p in self._patterns))
            brokers = self._mdns_list[:]
        return brokers

    def patterns_match(self, *patterns) -> bool:
        with self.lock:
            my_patterns = set(self._patterns)
        return my_patterns == set(patterns)


def splitServiceName(serviceName: str) -> Tuple[str, str]:
    """
    Split a full mDNS name (including service) into the base name and the
    service name.
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
    addr = info.parsed_addresses()[0]
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
                callback: Optional[Callable] = None) -> List[MDNSInfo]:
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
    for broker in mdns_finders:
        if broker.patterns_match(patterns):
            finder = broker
            break
    if finder is None:
        finder = MDNSFinder(*patterns, timeout=timeout)
        mdns_finders.append(finder)
        finder.start()
        deadline = time() + timeout

    while time() < deadline:
        if callback and callback():
            break
        if finder.get_brokers() and time() > scanDeadline:
            break
        sleep(0.1)
    return finder.get_brokers()


if __name__ == '__main__':
    from threading import Thread, active_count
    from random import randint

    def run_ad(name, delay, lifetime):
        from .advertising import Advertiser
        ad = Advertiser(name, rename=False)
        sleep(delay)
        ad.start()
        sleep(lifetime)
        ad.stop()

    finder = MDNSFinder()
    threads = []
    for i in range(20):
        threads.append(Thread(target=run_ad, args=(f"t{i:02}t{i:02}t{i:02}t{i:02}t{i:02}t{i:02}t{i:02}t{i:02}!!", randint(2,6), randint(4,20))))
    finder.start()
    start = time()
    print(f"Readt: {start}")
    for t in threads:
        t.start()
    print(f"starting: {time()}")
    started = False
    while started == False or active_count() > 1:
        if active_count() > 1:
            started = True
        found = finder.get_brokers()
        if any(not s.endswith('.local.') for s in found):
            print(f"Partial: {found}")

    print(f"done: {time()}")
    # def on_service_state_change(zeroconf, service_type, name, state_change):
    #     print(state_change, name)
    #
    # zc = Zeroconf()
    # browser = ServiceBrowser(
    #     zc,
    #     "_endaq._tcp.local.",
    #     handlers=[on_service_state_change],
    # )
    # while True:
    #     sleep(1)
