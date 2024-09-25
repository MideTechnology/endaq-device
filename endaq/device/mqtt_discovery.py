from dataclasses import dataclass
from fnmatch import fnmatchcase
from time import sleep, time
from typing import Callable, List, NamedTuple, Optional, Union

from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange


DEFAULT_NAME = "enDAQ Remote Interface"
DEFAULT_NAMES = ["enDAQ Remote Interface*", "Data Collection Box Interface*"]

@dataclass
class BrokerInfo:
    name: str
    address: str
    port: int
    properties: dict

    @classmethod
    def parse(cls, info):
        name = info.name.replace("._mqtt._tcp.local.", '')
        addr = info.parsed_addresses()
        props = {k: v for k, v in info.properties.items() if k}
        return cls(name, addr, props)


def _parseInfo(info):
    name = info.name.replace("._mqtt._tcp.local.", '')
    addr = info.parsed_addresses()
    props = {k: v for k, v in info.properties.items() if k}
    return  BrokerInfo(name, addr, info.port, props)


def findBroker(name: str = DEFAULT_NAME,
               timeout: float = 3):
    """
    Find a specific enDAQ-advertized MQTT Broker.

    :param name: The name of the broker.
    :param timeout:
    :return:
    """
    if not name.endswith("._mqtt._tcp.local."):
        name += "._mqtt._tcp.local."
    print(f'{name=}')
    r = Zeroconf()
    info = r.get_service_info("._mqtt._tcp.local.", name, timeout=timeout*1000)
    if not info:
        raise TimeoutError(f'MQTT Broker "{name}" not found')

    return BrokerInfo.parse(info)


def findBrokers(*patterns,
                scantime: float = 5,
                timeout: float = 2,
                callback: Optional[Callable] = None) -> List[BrokerInfo]:
    """
    Find enDAQ-advertized MQTT Brokers.

    :param patterns: Zero or more MQTT Broker names (multiple positional
        arguments). Glob-like wildcards may be used (case-sensitive).
        `None` will return all MQTT brokers.
    :param scantime: The minimum time (in seconds) to scan for brokers.
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
            if info:
                found.append(BrokerInfo.parse(info))

    _browser = ServiceBrowser(zeroconf, ["_mqtt._tcp.local."],
                              handlers=[on_service_state_change])

    deadline = time() + timeout
    scanDeadline = time() + scantime
    while time() < deadline:
        if callback and callback():
            break
        if not found and time() > scanDeadline:
            break
        sleep(0.01)

    if not found:
        raise TimeoutError(f'No MQTT Brokers found')

    if patterns:
        return [info for info in found
                if any(fnmatchcase(info.name, p) for p in patterns)]
    return found