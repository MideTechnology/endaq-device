"""
Find an enDAQ MQTT broker.
"""

from dataclasses import dataclass
from fnmatch import fnmatchcase
from time import sleep, time
from typing import Any, Callable, Dict, List, Optional

from zeroconf import Zeroconf, ServiceBrowser, ServiceInfo, ServiceStateChange


# ===========================================================================
#
# ===========================================================================

# DEFAULT_NAME = "enDAQ Remote Interface"
DEFAULT_NAME = "Data Collection Box Interface"
DEFAULT_NAMES = ["enDAQ Remote Interface*", "Data Collection Box Interface*"]
SERVICE_TYPE = "_endaq._tcp.local."

# ===========================================================================
#
# ===========================================================================

def parseInfo(info: ServiceInfo,
              serviceType: str = SERVICE_TYPE) -> Dict[str, Any]:
    """
    Parse `zeroconf.ServiceInfo` into a dictionary (for use elsewhere as
    keyword arguments). Resulting dictionary contains items `"name"`
    (string), `"host"` (list of addresses as strings, IPv4 and IPV6 if
    available), `"port"` (int), and `"properties"` (dictionary, provided
    by the service).
    """
    name = info.name.replace(f".{serviceType}", '')
    addr = info.parsed_addresses()
    # Some services' properties contain null keys
    props = {k: v for k, v in info.properties.items() if k}
    return {"name": name, "serviceType": serviceType,
            "host": addr, "port": info.port, "properties": props}


def getBroker(name: str = DEFAULT_NAME,
              serviceType: str = SERVICE_TYPE,
              timeout: float = 5) -> Dict[str, Any]:
    """
    Find a specific enDAQ-advertized MQTT Broker. In the best case, this may
    be marginally faster than `findBrokers()` when looking for a specific
    broker.

    :param name: The name of the broker.
    :param serviceType: The name of the service type under which the brokers
        will be advertised.
    :param timeout: The timeout, in seconds.
    :return: A dictionary of broker information.
    """
    if not name.endswith(serviceType):
        name = f'{name}.{serviceType}'

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
                serviceType: str = SERVICE_TYPE,
                scantime: float = 2,
                timeout: float = 5,
                callback: Optional[Callable] = None) -> List[Dict[str, Any]]:
    """
    Find enDAQ-advertized MQTT Brokers.

    :param patterns: Zero or more MQTT Broker names (multiple positional
        arguments). Glob-like wildcards may be used (case-sensitive).
        `None` will return all MQTT brokers.
    :param serviceType: The name of the service type under which the brokers
        will be advertised.
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
                found.append(parseInfo(info, serviceType))

    try:
        browser = ServiceBrowser(zeroconf, [serviceType],
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
