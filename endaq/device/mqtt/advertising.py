"""
This module contains the `Advertiser` class, used by the `MQTTDeviceManager`
to announce the name and IP address of the MQTT Broker via zeroconf/mDNS.
"""

import itertools
import json
import logging
import socket
from time import time, sleep
from typing import Any, Callable, Dict, Optional

from zeroconf import IPVersion, ServiceInfo, Zeroconf
from zeroconf import NonUniqueNameException

from .mqtt_interface import MQTT_BROKER, MQTT_PORT
from .discovery import DEFAULT_NAME, splitServiceName, findBrokers
from ..util import getMyIP

from endaq.device import __version__

logger = logging.getLogger(__name__)


class Advertiser:
    """
    A object that does mDNS service advertising of the MQTT broker.
    """

    def __init__(self,
                 name: str = DEFAULT_NAME,
                 rename: bool = True,
                 address: Optional[str] = MQTT_BROKER,
                 port: int = MQTT_PORT,
                 notes: Optional[str] = None,
                 properties: Optional[Dict[str, Any]] = None,
                 **kwargs):
        """
        An object to manage mDNS service advertising of the MQTT broker.

        :param name: The name of the service. Must be unique.
        :param address: The broker's address. Defaults to the machine running
            the Advertiser.
        :param port: The broker's port number.
        :param notes: An optional description of the broker/manager; if
            provided, the notes will be included in the service advertising.
        :param properties: An optional dictionary of additional data to be
            included in the service advertising.
        """
        if kwargs:
            logger.debug(f'Starting Advertiser, ignoring extra kwargs {kwargs}')
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
        self.zeroconf = None


    def stop(self) -> bool:
        """
        Stop advertising the MQTT broker.
        :return: True if the advertisement was stopped.
        """
        logger.debug('Attempting to stop advertising...')
        if self.zeroconf is None:
            return True
        self.zeroconf.unregister_service(self.info)
        self.zeroconf.close()
        self.zeroconf = None
        return True


    def start(self) -> None:
        """ Start the advertising activity.

        This method will raise a `RuntimeError` if called more than once on the
        same `Advertiser` object.
        """
        logger.debug(f'Starting zeroconf advertising of {self.fullName} '
                     f'on {self.address}:{self.port}.')
        if self.zeroconf is not None:
            raise RuntimeError('Advertising already started.')

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
    kwargs = vars(args).copy()
    kwargs.pop('config')

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
