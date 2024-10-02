import socket
from threading import Event, Thread
from time import time, sleep
from typing import Any, Callable, Dict, Optional

from zeroconf import IPVersion, ServiceInfo, Zeroconf

from .mqtt_interface import MQTT_BROKER, MQTT_PORT, getMyIP
from .mqtt_discovery import DEFAULT_NAME


class Advertiser(Thread):
    """
    A thread that does mDNS service advertising of the MQTT broker.
    """

    def __init__(self,
                 name: str = DEFAULT_NAME,
                 address: Optional[str] = MQTT_BROKER,
                 port: int = MQTT_PORT,
                 properties: Optional[Dict[str, Any]] = None):
        """
        A thread that does mDNS service advertising of the MQTT broker.

        :param name: The name of the service. Must be unique.
        :param address: The broker's address. Defaults to the machine running
            the advertising thread.
        :param port: The broker's port number.
        :param properties: An optional dictionary of additional data to be
            included in the service advertising.
        """
        self.port = port
        self.serviceName = name
        if not name.endswith("_mqtt._tcp.local."):
            name += "._mqtt._tcp.local."
        self.properties = properties or {}

        # TODO: IPv6 support?
        self.address = address or getMyIP()
        self.ipVersion = IPVersion.V4Only

        self.info = ServiceInfo(
                "_mqtt._tcp.local.",
                name,
                addresses=[socket.inet_aton(self.address)],
                port=self.port,
                properties=self.properties,
        )

        self._stopEvent = Event()
        super().__init__(daemon=True)
        self.name = self.name.replace("Thread", type(self).__name__)


    def stop(self,
             timeout: float = 10,
             callback: Optional[Callable] = None) -> bool:
        """
        Stop advertising the MQTT broker.

        :param timeout: Time to wait for the thread to shut down. 0 will
            return immediately. `None` will wait indefinitely.
        :param callback: A function to call repeatedly while waiting for the
            thread to stop. If the callback returns `True`, the wait will be
            cancelled. The callback function should require no arguments.
        :return: Whether the thread was stopped. Note: if `timeout` is 0,
            a false negative may occur.
        """
        timeout = -1 if timeout is None else timeout
        deadline = timeout + time()

        self._stopEvent.set()
        sleep(0.01)

        while timeout != 0 and self.is_alive():
            if timeout > 0 and time() > deadline:
                raise TimeoutError('Timed out trying to shut down advertiser')
            if callback and callback():
               break
            sleep(0.01)

        return not self.is_alive()


    def run(self):
        """
        Main thread.
        """
        zeroconf = Zeroconf(ip_version=self.ipVersion)
        zeroconf.register_service(self.info)

        try:
            while not self._stopEvent.is_set():
                sleep(0.1)
        finally:
            zeroconf.unregister_service(self.info)
            zeroconf.close()


# ===========================================================================
#
# ===========================================================================

