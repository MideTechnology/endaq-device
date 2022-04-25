"""
Error codes and exceptions related to the wi-fi. Specifically, the ESP32
used in the enDAQ "W" series recorders.

Error codes are from
https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-guides/wifi.html#wi-fi-reason-code
"""

from .exceptions import DeviceError


ERR_UNSPECIFIED = 1
ERR_AUTH_EXPIRE = 2
ERR_AUTH_LEAVE = 3
ERR_ASSOC_EXPIRE = 4
ERR_ASSOC_TOOMANY = 5
ERR_NOT_AUTHED = 6
ERR_NOT_ASSOCED = 7
ERR_ASSOC_LEAVE = 8
ERR_ASSOC_NOT_AUTHED = 9
ERR_DISASSOC_PWRCAP_BAD = 10
ERR_DISASSOC_SUPCHAN_BAD = 11
ERR_IE_INVALID = 13
ERR_MIC_FAILURE = 14
ERR_4WAY_HANDSHAKE_TIMEOUT = 15
ERR_GROUP_KEY_UPDATE_TIMEOUT = 16
ERR_IE_IN_4WAY_DIFFERS = 17
ERR_GROUP_CIPHER_INVALID = 18
ERR_PAIRWISE_CIPHER_INVALID = 19
ERR_AKMP_INVALID = 20
ERR_UNSUPP_RSN_IE_VERSION = 21
ERR_INVALID_RSN_IE_CAP = 22
ERR_802_1X_AUTH_FAILED = 23
ERR_CIPHER_SUITE_REJECTED = 24
ERR_BEACON_TIMEOUT = 200
ERR_NO_AP_FOUND = 201
ERR_AUTH_FAIL = 202
ERR_ASSOC_FAIL = 203
ERR_HANDSHAKE_TIMEOUT = 204
ERR_CONNECTION_FAIL = 205

errorcode = {
    1: 'ERR_UNSPECIFIED',
    2: 'ERR_AUTH_EXPIRE',
    3: 'ERR_AUTH_LEAVE',
    4: 'ERR_ASSOC_EXPIRE',
    5: 'ERR_ASSOC_TOOMANY',
    6: 'ERR_NOT_AUTHED',
    7: 'ERR_NOT_ASSOCED',
    8: 'ERR_ASSOC_LEAVE',
    9: 'ERR_ASSOC_NOT_AUTHED',
    10: 'ERR_DISASSOC_PWRCAP_BAD',
    11: 'ERR_DISASSOC_SUPCHAN_BAD',
    13: 'ERR_IE_INVALID',
    14: 'ERR_MIC_FAILURE',
    15: 'ERR_4WAY_HANDSHAKE_TIMEOUT',
    16: 'ERR_GROUP_KEY_UPDATE_TIMEOUT',
    17: 'ERR_IE_IN_4WAY_DIFFERS',
    18: 'ERR_GROUP_CIPHER_INVALID',
    19: 'ERR_PAIRWISE_CIPHER_INVALID',
    20: 'ERR_AKMP_INVALID',
    21: 'ERR_UNSUPP_RSN_IE_VERSION',
    22: 'ERR_INVALID_RSN_IE_CAP',
    23: 'ERR_802_1X_AUTH_FAILED',
    24: 'ERR_CIPHER_SUITE_REJECTED',
    200: 'ERR_BEACON_TIMEOUT',
    201: 'ERR_NO_AP_FOUND',
    202: 'ERR_AUTH_FAIL',
    203: 'ERR_ASSOC_FAIL',
    204: 'ERR_HANDSHAKE_TIMEOUT',
    205: 'ERR_CONNECTION_FAIL'
}


class WiFiError(DeviceError):
    """ Exception raised after a W device reports a Wi-Fi error.

        Usage:
        `WiFiError()`
        `WiFiError(ERR_IE_INVALID)`
        `WiFiError(ERR_AUTH_FAIL, "Failed to authorize")`
        `WiFiError(ERR_CONNECTION_FAIL, "Failed to connect", "192.168.0.1")`
    """

    def __init__(self, *args):
        super(WiFiError, self).__init__(*args)
        self.errno = None if not args else args[0]
        self.message = args[1] if len(args) > 1 else ''


    def __str__(self):
        msg = "[{}: {}] {}".format(self.errno,
                                   errorcode.get(self.errno, "(unknown)"),
                                   self.message)

        if len(self.args) > 2:
            msg = "{} {!r}".format(msg, self.args[2:])

        return msg.strip()


    def __repr__(self):
        try:
            if self.args:
                args = [repr(a) for a in self.args]
                args[0] = errorcode.get(self.errno, repr(self.errno))
                return "{}({})".format(type(self).__name__, ', '.join(args))
        except:
            # Just in case. __repr__() shouldn't ever fail.
            pass

        return super().__repr__()


# Status codes reported in <WiFiConnectionStatus>
STATUS_IDLE = 0
STATUS_PENDING = 1
STATUS_CONNECTED = 2
