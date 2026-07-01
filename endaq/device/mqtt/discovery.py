"""
Find an enDAQ MQTT broker.
"""

from fnmatch import fnmatchcase
import re
from time import sleep, time
from typing import Any, Callable, Dict, List, Optional, Tuple
from threading import Lock

from zeroconf import Zeroconf, ServiceBrowser, ServiceInfo, ServiceStateChange

from ..util import levenshtein

class MDNSFinder:
    _zc = None
    lock = Lock()
    _mdns_list = []

    @classmethod
    def _on_service_state_change(cls, zeroconf: Zeroconf,
                                service_type: str,
                                name: str,
                                state_change: ServiceStateChange):
        print(f"Called {name} ({service_type}), {state_change}")
        if state_change == ServiceStateChange.Removed:
            with cls.lock:
                if name in cls._mdns_list:
                    cls._mdns_list.remove(name)
            return
        info = zeroconf.get_service_info(service_type, name)
        if not info:
            print(f"getinfo failed for {name} ({service_type}) ")
            return
        with cls.lock:
            if name not in cls._mdns_list:
                cls._mdns_list.append(name)

    @classmethod
    def start(cls):
        if cls._zc is not None:
            return
        cls._zc = Zeroconf()
        cls.browser = ServiceBrowser(
            cls._zc,
            "_endaq._tcp.local.",
            handlers=[cls._on_service_state_change],
        )

    @classmethod
    def close(cls):
        cls._zc.close()
        cls._zc = None
        with cls.lock:
            cls._mdns_list = []

    @classmethod
    def get_brokers(cls):
        # with cls.lock:
        brokers = cls._mdns_list
        return brokers

# ===========================================================================
#
# ===========================================================================

# DEFAULT_NAME = "enDAQ Remote Interface._endaq._tcp.local."
DEFAULT_NAME = "Data Collection Box Interface._endaq._tcp.local."
DEFAULT_NAMES = ["enDAQ Remote Interface*._endaq._tcp.local.",
                 "Data Collection Box Interface*._endaq._tcp.local."]
SERVICE_TYPE = "_endaq._tcp.local."

# ===========================================================================
#
# ===========================================================================


def splitServiceName(serviceName: str) -> Tuple[str, str]:
    """
    Split a full mDNS name (including service) into the base name and the
    service name.
    """
    if m := re.match(r"(.+)\.(.+\._tcp\.local\.)", serviceName):
        return m.groups()
    return serviceName, SERVICE_TYPE


def parseInfo(info: ServiceInfo) -> Dict[str, Any]:
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
    return {"name": name, "serviceType": serviceType,
            "host": addr, "port": info.port, "properties": props}


def getBroker(name: str = DEFAULT_NAME,
              timeout: float = 5) -> Dict[str, Any]:
    """
    Find a specific enDAQ-advertised MQTT Broker. In the best case, this may
    be marginally faster than `findBrokers()` when looking for a specific
    broker.

    :param name: The name of the broker.
    :param timeout: The timeout, in seconds.
    :return: A dictionary of broker information.
    """
    _basename, serviceType = splitServiceName(name)

    zeroconf = Zeroconf()
    try:
        info = zeroconf.get_service_info(serviceType, name,
                                         timeout=timeout*1000)
        if not info:
            raise TimeoutError(f'MQTT Broker "{name}" not found')

        return parseInfo(info)

    finally:
        zeroconf.close()


def findBrokers(*patterns,
                scantime: float = 2,
                timeout: float = 5,
                callback: Optional[Callable] = None) -> List[Dict[str, Any]]:
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
    if not patterns:
        patterns = DEFAULT_NAMES[:]
    elif patterns[0] is None:
        patterns = None
    else:
        # Add service name if the name doesn't have one.
        patterns = list(patterns)
        for i, n in enumerate(patterns):
            patterns[i] = '{}.{}'.format(*splitServiceName(n))

    found = []
    zeroconf = Zeroconf()

    def on_service_state_change(zeroconf: Zeroconf,
                                service_type: str,
                                name: str,
                                state_change: ServiceStateChange):
        if state_change != ServiceStateChange.Removed:
            info = zeroconf.get_service_info(service_type, name)
            if not info:
                return
            if not patterns or any(fnmatchcase(info.name, p) for p in patterns):
                found.append(parseInfo(info))

    try:
        if not patterns:
            services = [SERVICE_TYPE]
        else:
            services = [splitServiceName(n)[1] for n in patterns]
        browser = ServiceBrowser(zeroconf, services,
                                 handlers=[on_service_state_change])

        deadline = time() + timeout
        scanDeadline = time() + scantime
        while time() < deadline:
            if callback and callback():
                break
            if found and time() > scanDeadline:
                break
            sleep(0.1)

        browser.cancel()
        if patterns and len(found) > 1:
            # Sort by similarity to patterns
            found.sort(key=lambda x: min(levenshtein(x['name'], p)
                                         for p in patterns))
        return found

    finally:
        zeroconf.close()

from threading import Thread, active_count
from random import randint

def run_ad(name, delay, lifetime):
    from .advertising import Advertiser
    ad = Advertiser(name, rename=False)
    sleep(delay)
    ad.start()
    sleep(lifetime)
    ad.stop()

if __name__ == '__main__':
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
