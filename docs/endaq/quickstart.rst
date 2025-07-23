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
   import os.path
   import shutil
   import endaq.device
   from endaq.device.exceptions import CommandError, DeviceTimeout

   # Find all connected devices and print their serial numbers
   device_list = endaq.device.getDevices()
   print("Connected Device Serial Number(s):")
   for device in device_list:
      print(device.serial)

   # Select the first device from the list of available devices
   dev = endaq.device.getDevices()[0]

   # Update configuration
   dev.config.setSampleRate(dev.channels[80], 4000)  # Set Ch 80 SR to 4000 Hz
   dev.config.retrigger = False # Turn off retrigger
   if dev.firmwareVersion < 30106:
      dev.config.recordingTimeLimit = 30 # Set recording limit to 30s for old FW

   # Start Recording
   dev.command.startRecording()

   # For older devices without a SerialCommandInterface
   if not isinstance(dev.command, endaq.device.SerialCommandInterface):
         print("Start command failed, please push the button to start a recording.")
         dev.command.awaitDisconnect() # Wait for the device to disconnect

   # Stop Recording
   if dev.firmwareVersion >= 30106:
      time.sleep(30)
      dev.command.stopRecording()
   else:
      if dev.command.awaitReconnect(timeout=60) ==  False:
         raise DeviceTimeout("Device did not reconnect in 60 seconds after recording.")

   # Copy the most recent recording on the enDAQ to your local directory
   destination = "/destination/" # Replace with desired destination path

   path = os.path.join(dev.path, 'DATA', 'RECORD')
   newest = sorted(os.listdir(path))[-1]
   shutil.copy2(os.path.join(path, newest), os.path.join(destination, newest))
   # Print the copied file's name
   print(f"Name of the most recent recording: {newest}")

