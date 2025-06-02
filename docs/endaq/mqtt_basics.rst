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

* In Windows, you may need to explicitly state the path to the ``mosquitto`` executable, e.g., ``'C:\Program Files\mosquitto\mosquitto.exe'``
* ``-v`` turns on verbose output and is optional.
* ``-c`` specifies the confgiguration file to use. If you are not in the directory containing your ``mosquitto.conf``, you will need to provide its full path.

Start the MQTT Device Manager and Advertising
---------------------------------------------
On the command line in another shell/terminal window, enter:

.. code-block::

    python -m endaq.device.mqtt.manager

- If the MQTT Broker is running on a different computer, you will need to specify it by name or IP address, e.g.:
  ``python -m endaq.device.mqtt.manager -a 192.160.0.100``

Configure the enDAQ device
--------------------------

.. image:: ../_static/mqtt_config.png

TODO: Screenshots and stuff

Create an MQTTConnector and get a Recorder
------------------------------------------
:class:`~.mqtt.mqtt_interface.MQTTConnector` handles communication with the MQTT broker, and presents

In the Python interactive console/REPL (run from the command line in another shell/terminal window, through an IDE, etc.):

.. code-block:: python

    >>> from endaq.device.mqtt.mqtt_interface import MQTTConnector
    >>> con = MQTTConnector.find()
    >>> con.getDevices()
    [<EndaqW W8-E100D40 "Test device #1" SN:W0016827 (remote)>]
    >>>

