"""
This module contains the `Advertiser` class, used by the `MQTTDeviceManager`
to announce the name and IP address of the MQTT Broker via zeroconf/mDNS.
"""

import itertools
import json
import logging
import socket
from threading import Event, Thread
from time import time, sleep
from typing import Any, Callable, Dict, Optional

from zeroconf import IPVersion, ServiceInfo, Zeroconf
from zeroconf import NonUniqueNameException

from .mqtt_interface import MQTT_BROKER, MQTT_PORT
from .discovery import DEFAULT_NAME, splitServiceName, findBrokers
from ..util import getMyIP

from endaq.device import __version__

logger = logging.getLogger(__name__)


class Advertiser(Thread):
    """
    A thread that does mDNS service advertising of the MQTT broker.
    """

    def __init__(self,
                 name: str = DEFAULT_NAME,
                 rename: bool = True,
                 address: Optional[str] = MQTT_BROKER,
                 port: int = MQTT_PORT,
                 notes: Optional[str] = None,
                 properties: Optional[Dict[str, Any]] = None):
        """
        A thread that does mDNS service advertising of the MQTT broker.

        :param name: The name of the service. Must be unique.
        :param address: The broker's address. Defaults to the machine running
            the advertising thread.
        :param port: The broker's port number.
        :param notes: An optional description of the broker/manager; if
            provided, the notes will be included in the service advertising.
        :param properties: An optional dictionary of additional data to be
            included in the service advertising.
        """
        self.port = port
        self.rename = rename
        self.serviceName, self.serviceType = splitServiceName(name)
        self.properties = properties or {}
        self.fullName = f'{self.serviceName}.{self.serviceType}'

        self.properties['manager_version'] = __version__

        if notes:
            self.properties['notes'] = notes

        # TODO: IPv6 support?
        self.address = address or getMyIP()
        self.ipVersion = IPVersion.V4Only

        self.info = ServiceInfo(
                self.serviceType,
                self.fullName,
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
        logger.debug('Attempting to stop advertising...')
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

        stopped = not self.is_alive()
        if stopped:
            logger.debug('Advertiser shut down.')
        else:
            logger.warning('Failed to shut down advertiser within {timeout} seconds!')

        return stopped


    def start(self) -> None:
        """ Start the advertising thread's activity.

        It must be called at most once per thread object. It arranges for the
        object's run() method to be invoked in a separate thread of control.

        This method will raise a `RuntimeError` if called more than once on the
        same `Advertiser` object.
        """
        logger.debug(f'Starting zeroconf advertising of {self.fullName} '
                     f'on {self.address}:{self.port}.')
        self.zeroconf = Zeroconf(ip_version=self.ipVersion)

        existing = findBrokers(None)
        basename = self.serviceName

        if self.rename:
            for n in itertools.count(1):
                self.info = ServiceInfo(
                        self.serviceType,
                        self.fullName,
                        addresses=[socket.inet_aton(self.address)],
                        port=self.port,
                        properties=self.properties)
                try:
                    # Duplicate names (apparently) allowed on different
                    # segments of same network (e.g., ethernet adn Wi-Fi);
                    # explicitly check for duplicates
                    if not any(broker['name'] == self.serviceName for broker in existing):
                        self.zeroconf.register_service(self.info)
                        break
                except NonUniqueNameException:
                    continue

                self.serviceName = f'{basename} {n}'
                self.fullName = f'{self.serviceName}.{self.serviceType}'
                logger.info(f'Name not unique, trying {self.fullName}')
        else:
            if any(broker['name'] == self.serviceName for broker in existing):
                raise NonUniqueNameException
            self.zeroconf.register_service(self.info)

        super().start()


    def run(self):
        """
        Main thread.
        """
        try:
            while not self._stopEvent.is_set():
                sleep(0.25)

        finally:
            logger.debug(f'Ending zeroconf advertising of {self.fullName} '
                         f'on {self.address}:{self.port}.')
            self.zeroconf.unregister_service(self.info)
            self.zeroconf.close()


# ===========================================================================
#
# ===========================================================================

if __name__ == '__main__':
    import argparse

    desc = __doc__ + ("\n\nDo not run if the MQTTDeviceManager is already advertising "
                      "(e.g., endaq.device.mqtt.manager run without the '--silent' option).")
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('-a', '--address', type=str, default=None,
                        help="MQTT Broker address/hostname. Defaults to this machine.")
    parser.add_argument('-p', '--port', type=int, default=MQTT_PORT,
                        help="MQTT Broker port.")
    parser.add_argument('-n', '--name', type=str, default=DEFAULT_NAME,
                        help="The advertised name of the MQTT broker.")
    parser.add_argument('-r', '--rename', action='store_true',
                        help="Add an incrementing number to the advertised name "
                             "if that name is already in use.")
    parser.add_argument('-c', '--config', type=str, default=None, metavar="FILENAME",
                        help="The name of a configuration JSON file with additional "
                             "arguments for the advertising. Values in the config file "
                             "will override other arguments. Can be the same file used "
                             "to start the device manager; extra arguments will be ignored.")

    args = parser.parse_args()
    kwargs = vars(args)

    if args.config:
        with open(args.config, 'r') as f:
            config = json.load(f)
            kwargs.update(config)

    advertiser = Advertiser(**kwargs)
    print(f'Advertising "{advertiser.fullName}" ({advertiser.address} port {advertiser.port})')
    advertiser.start()

    try:
        while True:
            sleep(60)
    except KeyboardInterrupt:
        print('Advertising shutting down...')
        advertiser.stop()
