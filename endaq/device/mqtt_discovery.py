"""
Find an enDAQ MQTT broker.
"""

from dataclasses import dataclass
from fnmatch import fnmatchcase
from time import sleep, time
from typing import Callable, List, Optional

from zeroconf import Zeroconf, ServiceBrowser, ServiceInfo, ServiceStateChange


# ===========================================================================
#
# ===========================================================================

DEFAULT_NAME = "enDAQ Remote Interface"
DEFAULT_NAMES = ["enDAQ Remote Interface*", "Data Collection Box Interface*"]


# ===========================================================================
#
# ===========================================================================

@dataclass
class BrokerInfo:
    """ Information about discovered brokers. """
    name: str
    address: str
    port: int
    properties: dict

    @classmethod
    def parse(cls, info: ServiceInfo) -> "BrokerInfo":
        """ ServiceInfo -> BrokerInfo """
        name = info.name.replace("._mqtt._tcp.local.", '')
        addr = info.parsed_addresses()
        # Some services' properties contain null keys
        props = {k: v for k, v in info.properties.items() if k}
        return cls(name, addr, info.port, props)


def getBroker(name: str = DEFAULT_NAME,
              timeout: float = 5) -> BrokerInfo:
    """
    Find a specific enDAQ-advertized MQTT Broker. In the best case, this may
    be marginally faster than `findBrokers()`.

    :param name: The name of the broker.
    :param timeout: The timeout, in seconds.
    :return: The broker information.
    """
    if not name.endswith("._mqtt._tcp.local."):
        name += "._mqtt._tcp.local."

    r = Zeroconf()
    try:
        info = r.get_service_info("._mqtt._tcp.local.", name, timeout=timeout*1000)
        if not info:
            raise TimeoutError(f'MQTT Broker "{name}" not found')

        return BrokerInfo.parse(info)

    finally:
        r.close()


def findBrokers(*patterns,
                scantime: float = 2,
                timeout: float = 5,
                callback: Optional[Callable] = None) -> List[BrokerInfo]:
    """
    Find enDAQ-advertized MQTT Brokers.

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
    if patterns and patterns[0] is None:
        patterns = None
    else:
        patterns = patterns or DEFAULT_NAMES[:]

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
                found.append(BrokerInfo.parse(info))

    try:
        browser = ServiceBrowser(zeroconf, ["_mqtt._tcp.local."],
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
        return found

    finally:
        zeroconf.close()
