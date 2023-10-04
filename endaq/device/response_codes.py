"""
Response codes to various commands. Responses from the device are all
integers; these enumerations give them some context. This is important, as
some common numbers have different meanings in different types of response.

All response code values are interchangable with `int`, and function as
if they are subclasses of `int`. They can be used with integers in
comparisons and other expressions; they can even be used as array indices.
"""

from enum import IntEnum

__all__ = ("DeviceStatusCode", "WiFiConnectionStatus",
           "CurrentWiFiStatus", "WiFiConnectionError")


class DeviceStatusCode(IntEnum):
    """ The device status, returned in the response to a command. Negative
        values denote errors.
    """
    IDLE = 0  #: Device idle, message successful.
    RECORDING = 10  #: Device is currently recording.
    RESET_PENDING = 20  #: Reset pending: the device will reset soon after this response is received.
    START_PENDING = 30  #: Recording start pending: the device will start recording soon after this response is received.

    ERR_BUSY = -10  #: Communication channel is busy
    ERR_INVALID_COMMAND = -20  #: Badly formed command
    ERR_UNKNOWN_COMMAND = -30  #: Command not recognized
    ERR_BAD_PAYLOAD = -40  #: Command payload is bad
    ERR_BAD_EBML = -50  #: Command EBML is malformed
    ERR_BAD_CHECKSUM = -60  #: Command checksum failed (error transmitting packet)
    ERR_BAD_PACKET = -70  #: Content of command packet bad/damaged


class WiFiConnectionStatus(IntEnum):
    """ The status of the Wi-Fi connection, returned when querying Wi-Fi.
    """
    IDLE = 0  #: Wi-Fi is inactive (and/or disconnected).
    PENDING = 1  #: The device is in the process of connecting to the Wi-Fi AP.
    CONNECTED = 2  #: The device is connected to the Wi-Fi AP.


class CurrentWiFiStatus(IntEnum):
    """ More specific Wi-Fi connection status, returned when querying the
        network interface.
    """
    CONNECTION_FAILED = 0  #: Connection to the Wi-Fi AP has failed.
    CONNECTING = 1  #: The device is currently trying to connect to the Wi-Fi AP.
    CONNECTED = 2  #: The device is connected to the Wi-Fi AP, but not yet to enDAQ Cloud (or cloud connection status unknown).
    CONNECTED_CLOUD = 3  #: Connected to Wi-Fi and to enDAQ Cloud.


class WiFiConnectionError(IntEnum):
    """ ESP32 error codes, potentially returned when querying Wi-Fi.

        See: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-guides/wifi.html#wi-fi-reason-code
    """
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
