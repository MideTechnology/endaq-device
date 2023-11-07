"""
Classes for representing specific models of enDAQ data recoreder.
"""

__author__ = "dstokes"
__copyright__ = "Copyright 2023 Mide Technology Corporation"

import re
from typing import Callable, Optional, Union
import warnings

from .base import Recorder
from .exceptions import ConfigError, UnsupportedFeature


# ==============================================================================
# 
# ==============================================================================

class EndaqS(Recorder):
    """ An enDAQ S-series data recorder from Mide Technology Corporation. 
    """

    SN_FORMAT = "S%07d"
        
    manufacturer = "Midé Technology Corporation"
    homepage = "https://endaq.com/collections/endaq-shock-recorders-vibration-data-logger-sensors"

    _NAME_PATTERN = re.compile(r'(^S(\d|\d\d)-.*)|(^SF-DR4-(02|04))')


# ==============================================================================
# 
# ==============================================================================

class EndaqW(EndaqS):
    """ An enDAQ W-series wireless-enabled data recorder from Mide Technology Corporation.
    """
    SN_FORMAT = "W%07d"

    # Part number starts with "W", a 1-2 digit number, and "-"
    _NAME_PATTERN = re.compile(r'(^W(\d|\d\d)-.*)|(^SF-DR4-(01|03))')


    def setAP(self, ssid: str, password: Optional[str] = None):
        """ Quickly set the Wi-Fi access point (router) and password.

            :param ssid: The SSID (name) of the wireless access point.
            :param password: The access point password.
        """
        # FUTURE: Remove EndaqW.setAP()
        warnings.warn("Direct control moved to `command` attribute; use "
                      "recorder.command.setAP()", DeprecationWarning)

        if self.isVirtual:
            raise ConfigError('Cannot configure a virtual device')
        if not self.command:
            raise UnsupportedFeature('Device has no command interface')

        return self.command.setAP(ssid, password)


    def setWifi(self,
                wifi_data: dict,
                timeout: int = 10,
                interval: float = 1.25,
                callback: Optional[Callable] = None):
        """ Configure all known Wi-Fi access points. Applicable only
            to devices with Wi-Fi hardware. The data is in the form of a
            list of dictionaries with the following keys:

            * ``"SSID"``: The Wi-Fi access point name (string)
            * ``"Password"``: The access point's password (string, optional)
            * ``"Selected"``: 1 if the device should use this AP, 0 if not

            Note that devices may not support configuring multiple Wi-Fi AP.
            In most cases, only one should be specified, and it should be
            marked as selected.

            Note: This method is deprecated. Use `recorder.command.setWiFi()`
            instead.

            :param wifi_data: The information about the Wi-Fi networks to be
                set on the device.
            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will be
                cancelled. The callback function should take no arguments.
        """
        # FUTURE: Remove EndaqW.setWiFi()
        warnings.warn("Direct control moved to `command` attribute; use "
                      "recorder.command.setWiFi()", DeprecationWarning)

        if self.isVirtual:
            raise ConfigError('Cannot configure a virtual device')
        if not self.command:
            raise UnsupportedFeature('Device has no command interface')

        if not wifi_data:
            # For legacy code. CommandInterface version does not warn.
            warnings.warn("Use command.queryWifi() to get Wi-Fi status, "
                          "not setWifi(None)", DeprecationWarning)
            return self.command.queryWifi(timeout, interval / 5, callback)

        return self.command.setWifi(wifi_data=wifi_data,
                                    timeout=timeout,
                                    interval=interval,
                                    callback=callback)


    def queryWifi(self,
                  timeout: int = 10,
                  interval: float = .25,
                  callback: Optional[Callable] = None) -> Union[None, dict]:
        """ Check the current state of the Wi-Fi (if present).

            Note: This method is deprecated. Use `recorder.command.queryWiFi()`
            instead.

            :param timeout: Time (in seconds) to wait for a response before
                raising a `DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will be
                cancelled. The callback function should require no arguments.
            :return: None if no information was recieved, else it will return
                the information from the ``QueryWiFiResponse`` command (this
                return statement is not used anywhere)
        """
        # FUTURE: Remove EndaqW.queryWifi()
        warnings.warn("Direct control moved to `command` attribute; use "
                      "recorder.command.queryWifi()", DeprecationWarning)

        if self.isVirtual:
            raise ConfigError('Cannot configure a virtual device')
        if not self.command:
            raise UnsupportedFeature('Device has no command interface')

        return self.command.queryWifi(timeout=timeout, interval=interval, callback=callback)


    def scanWifi(self, timeout: int = 10,
                 interval: float = .25,
                 callback: Optional[Callable] = None) -> Union[None, list]:
        """ Initiate a scan for Wi-Fi access points (APs). Applicable only
            to devices with Wi-Fi hardware.

            The resluts are returned as a list of dictionaries, one for each
            access point, with keys:

            * ``SSID`` (str): The access point name.
            * ``RSSI`` (int): The AP's signal strength.
            * ``AuthType`` (int): The authentication (security) type.
              Currently, this is either 0 (no authentication) or 1
              (any authentication).
            * ``Known`` (bool): Is this access point known (i.e. has
              a stored password on the device)?
            * ``Selected`` (bool): Is this the currently selected AP?

            Note: This method is deprecated. Use `recorder.command.scanWiFi()`
            instead.

            :param timeout: Time (in seconds) to wait for a response before
                raising a :class:`~.endaq.device.DeviceTimeout` exception.
            :param interval: Time (in seconds) between checks for a response.
            :param callback: A function to call each response-checking cycle.
                If the callback returns `True`, the wait for a response will
                be cancelled. The callback function should take no arguments.
            :return: A list of dictionaries, described above.
        """
        # FUTURE: Remove EndaqW.scanWifi()
        warnings.warn("Direct control moved to `command` attribute; use "
                      "recorder.command.scanWifi()", DeprecationWarning)

        if self.isVirtual:
            raise ConfigError('Cannot configure a virtual device')
        elif not self.command:
            raise UnsupportedFeature('Device has no command interface')

        return self.command.scanWifi(timeout=timeout, interval=interval, callback=callback)


    def updateESP32(self,
                    firmware: str,
                    destination: Optional[str] = None,
                    timeout: float = 10,
                    callback: Optional[Callable] = None):
        """ Update the ESP32 firmware.

            Note: This method is deprecated. Use `recorder.command.updateESP32()`
            instead.

            :param firmware: The name of the ESP32 firmware package (.bin).
            :param destination: The name of the firmware package after being
                copied to the device, an alternative to the default.
                Optional; primarily for testing purposes.
            :param timeout: Time (in seconds) to wait for the recorder to
                respond. 0 will return immediately.
            :param callback: A function to call each response-checking
                cycle. If the callback returns `True`, the wait for a response
                will be cancelled. The callback function should take no
                arguments.
            :return:
        """
        # FUTURE: Remove EndaqW.updateESP32()
        warnings.warn("Direct control moved to `command` attribute; use "
                      "recorder.command.updateESP32()", DeprecationWarning)

        return self.command.updateESP32(firmware=firmware,
                                        destination=destination,
                                        timeout=timeout,
                                        callback=callback)
