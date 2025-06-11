===============================================
``endaq.device`` Concepts and Quick Start Guide
===============================================

Here are some concept summaries and common usage examples to help you get started with ``endaq.device``.

.. note::
  This documentation is in very early development.

Basic usage
===========

Finding attached devices
------------------------

An ``endaq.device`` "Hello World":

.. code-block:: python

   >>> import endaq.device
   >>> endaq.device.getDevices()
   [<EndaqS S3-E25D40 "Example S3" SN:S0009468 (D:\)>]

Accessing basic recorder properties
-----------------------------------

Most common properties are read-only attributes of :py:class:`endaq.device.Recorder`. ``getDevices()`` returns a list of
:py:class:`endaq.device.Recorder` objects, each of which represents a connected device (and not a virtual recorder). 
To access information about a single device, use indexing.

.. code-block:: python

   >>> dev = endaq.device.getDevices()[0]
   >>> dev.name
   'Example S3'
   >>> dev.serial
   'S0009468'
   >>> dev.hardwareVersion
   '2.0'

Some :py:class:`endaq.device.Recorder` properties are identical to those of an
`idelib.Dataset <https://mide-technology-idelib.readthedocs-hosted.com/en/feature-update-docs/idelib/dataset.html#idelib.dataset.Dataset>`_
(an imported recording file). These include:

* ``sensors``: The device's sensors, a dictionary of `idelib.Sensor` objects.
* ``channels``: The device's Channels, a dictionary of `idelib.Channel` objects.
* ``transforms``: The device's data conversion and calibration polynomials, as `idelib.transforms.Transform` objects.

.. code-block:: python

   >>> dev.channels
   {8: <Channel 8 '25g PE Acceleration': Acceleration (g)>, 80: <Channel 80 '40g DC Acceleration': Acceleration (g)>, 36: <Channel 36 'Pressure/Temperature': Pressure (Pa), Temperature (°C)>, 65: <Channel 65 'Absolute Orientation': Quaternion (q)>, 70: <Channel 70 'Relative Orientation': Quaternion (q)>, 47: <Channel 47 'Rotation': Rotation (dps)>, 59: <Channel 59 'Control Pad Pressure/Temperature/Humidity': Pressure (Pa), Temperature (°C), Relative Humidity (RH)>, 76: <Channel 76 'Light Sensor': Light (Ill), Light (Index)>}

Configuration
-------------

Configuration is done via the `configuration interface <config_control.html#configuration>`_.

.. code-block:: python

   >>> dev.config.enableChannel(dev.channels[8][0], True)
   >>> dev.config.setSampleRate(dev.channels[8], 3600)

Control
-------

Device control is done via the `command interface <config_control.html#control>`_. Virtual devices can not be commanded.

.. code-block:: python

   >>> dev.command.startRecording()

Virtual devices
===============
An enDAQ ``.IDE`` recording file can be used to create a 'virtual' version
of the recorder that created it. This provides an easy way to retrieve
information about the device and how it was configured.

.. code-block:: python

  >>> from idelib.importer import openFile
  >>> with openFile('test.ide') as doc:
  ...     virtual_dev = endaq.device.fromRecording(doc)

Quick Start Example Code
========================
Here is some starter code for introducing yourself to the endaq.device library. 
Use it to familiarize yourself with with how to use endaq.device and learn 
about some of its basic applications. Make sure to follow the 
`installation <index.html#installation>` instructions found on the homepage 
first. 

.. code-block:: python
   :linenos:
   
   """ 
   Quick Start example code for using the endaq.device library.
   """
   # Import endaq.device and other useful libraries.
   import time
   from idelib.importer import openFile
   import endaq.device

   # Select the first device from the list of available devices
   dev = endaq.device.getDevices()[0]

   # IGNORE commandWait() for now


   def commandWait(timeout):
      """ Wait for the device to reconnect after a command is sent.

         :param timeout: Time (seconds) to wait for the device to reconnect.
      """
      # 'commandWait': Function to call after using certain commands. It can be
      # ignored for now but is here for referencing later.
      #
      # When to use commandWait():
      # After commands like 'startRecording' or 'blink', for example, the device
      # will briefly disconnect and reconnect. If there is an attempt to run
      # another command during this period of time, then the serial port will not
      # be discoverable for the device. By waiting until the device reconnects and
      # monitoring the device's connection and status, this function ensures that
      # running one command after another is successful.

      for _ in range(int(timeout)):
         try:
               resp = dev.command.ping()
               print(f"Status code: {dev.command.status=}\t"
                     "message: {dev.command.status[1]}")
               if dev.command.status[1] == endaq.device.response_codes.DeviceStatusCode.RECORDING or \
                     dev.command.status[1] == endaq.device.response_codes.DeviceStatusCode.IDLE_UNMOUNTED:
                  print(
                     f"Device is recording. Status code: {dev.command.status[1]}")

         except Exception as e:
               print(f"Got error {e}")

         time.sleep(1)


   # Accessing basic properties about the device:
   # This is done by calling different properties of our instance of
   # the Recorder class called "dev".
   print("PROPERTIES")
   print("Device Name:", dev.name)
   print("Device Serial Number:", dev.serial)
   print("Device Hardware Version:", dev.hardwareVersion)
   print("Device Firmware Version:", dev.firmwareVersion)
   print("Device Channels:", dev.channels)
   # To view all possible properties to access, look at the "The Recorder Class"
   # section of the documentation.

   # Some basic configurations:
   print("\nCONFIGURATION")
   print("Device ready for configuration:", dev.config.available)
   dev.config.enableChannel(dev.channels[80], False)  # Disable Ch 80
   dev.config.enableChannel(dev.channels[80])
   dev.config.setSampleRate(dev.channels[80], 1000)  # Set Ch 80 SR to 1000 Hz
   print("New Channel 80 Sample Rate:",
         dev.config.getSampleRate(dev.channels[80]))
   dev.config.revert()  # Revert to default original configuration
   print("Original Channel 80 Sample Rate:",
         dev.config.getSampleRate(dev.channels[80]))
   print("Settable triggers for Channel 80:",
         dev.config.getTrigger(dev.channels[80]))
   print("Settable triggers for all channels:", dev.config.getTriggers())
   dev.config.setTrigger(dev.channels[80], high=20)
   dev.config.applyConfig()
   # To view all possible configurations, look at the "Configuration and Control"
   # section of the documentation.

   # Some basic commands:
   # Note: Commands can only be sent to a physical enDAQ device;
   # They will not work on Virtual Devices (imported .IDE files).
   print("\nCOMMANDS")
   print("Device ready for commands:", dev.command.available)
   print("Device Battery Status:", dev.command.getBatteryStatus())
   print("Device Clock Drift:", dev.command.getClockDrift())
   print("Device Time:", dev.command.getTime())
   dev.command.setTime()  # Set the device time to the computer's time
   dev.command.blink()  # Blink the device's LEDs
   # 'blink()' is helpful for identifying a specific device when multiple devices
   # are plugged in to one computer
   commandWait(10)  # Defined above! Waits and prints useful information.
   dev.command.startRecording()
   commandWait(10)
   print("Recording stopped:", dev.command.stopRecording())
   # To view all possible commands, look at the "Configuration and Control" section
   # of the documentation.

   # Virtual Devices:
   # Using a recording file to create a 'virtual' version of the recorder that created it.
   # Useful for discovering device information but can't be used to run commands.
   with openFile('test.ide') as doc:
      virtual_dev = endaq.device.fromRecording(doc)
