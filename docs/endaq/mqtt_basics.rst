=========================
``endaq.device`` and MQTT
=========================
.. default-domain:: py
.. currentmodule:: endaq.device

Controlling and communicating with Wi-Fi enabled enDAQ devices is done via `MQTT <https://mqtt.org/>`_,
a lightweight protocol widely used in IoT applications.

Setup
~~~~~
A full setup for communicating with an enDAQ device over MQTT consists of three parts:

1. An **MQTT Broker**. ``endaq.device`` requires the presence of a running MQTT broker supporting version 5.x of the protocol. The MQTT broker is *not* included in ``endaq.device`` and must be downloaded and installed separately. One such broker is `Mosquitto <https://mosquitto.org/>`_; its open source version (EPL/EDL license) is cross-platform, small, and can be run locally or on a server. The specific details of setting up the MQTT broker is beyond the scope of this document; consult the Broker's documentation for more information.

2. An **enDAQ Device Manager**. :class:`~.mqtt.manager.MQTTDeviceManager` is a thread/process, typically running in the background, that keeps track of devices connected via MQTT. It connects to the Broker and provides enDAQ-specific functionality, such as aiding in device discovery and tracking sleeping devices. Another feature the Device Manager provides is *advertising,* so the enDAQ devices and :class:`~.mqtt.mqtt_interface.MQTTConnector` (described below) can find the Broker. This can be run on the same machine as the MQTT Broker; for small setups and tests, it can be run locally.

3. An **MQTT Connector**. :class:`~.mqtt.mqtt_interface.MQTTConnector` is the user-facing component that handles communicating with the Broker and Device Manager. Its primary function is creating and handling :class:`~.Recorder` instances for MQTT-enabled devices.

Each component can be run on different machines, but the machines must be on the same network.

Quick Start
~~~~~~~~~~~

Start the MQTT Broker
---------------------
The specifics of how you start the Broker depend on which Broker you installed, and how and where it was installed. These instructions assume Mosquitto has been installed and is not currently running.

Create a ``mosquitto.conf`` file
''''''''''''''''''''''''''''''''
If you have not previously created a Mosquitto configuration file, you will need to do so. Here is a simple ``mosquitto.conf`` file:

.. code-block::

    listener 1883 0.0.0.0
    allow_anonymous true

Start Mosquitto in 'user space'
'''''''''''''''''''''''''''''''

Starting Mosquitto in a standard user process (as opposed to running as a system service) is nearly identical in Linux, MacOS, and Windows. On a shell command line, enter:

.. code-block::

    mosquitto -v -c mosquitto.conf

* ``-v`` turns on verbose output and is optional.
* In Windows, you may need to explicitly state the path to the ``mosquitto`` executable, e.g., ``'C:\Program Files\mosquitto\mosquitto.exe'``
* Similarly, if you are not in the directory containing ``mosquitto.conf``, you will need to provide its full path.

Configure the enDAQ device
--------------------------

Start the MQTT Device Manager and Advertising
---------------------------------------------

Create an MQTTConnector and get a Recorder
------------------------------------------


