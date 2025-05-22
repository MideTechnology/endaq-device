=========================
``endaq.device`` and MQTT
=========================

Controlling and communicating with Wi-Fi enabled enDAQ devices is done via `MQTT <https://mqtt.org/>`_,
a lightweight protocol widely used in IoT applications. ``endaq.device`` requires the presence of a running
MQTT broker supporting version 5.x of the protocol. The MQTT broker is not included in ``endaq.device`` and
must be downloaded and installed separately. One such broker is `Mosquitto <https://mosquitto.org/>`_;
its open source version (EPL/EDL license) is cross-platform, small, and can be run locally.


