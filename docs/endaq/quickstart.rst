===============================================
``endaq.device`` Concepts and Quick Start Guide
===============================================

.. note::
  This documentation is in very early development.

Basic usage
===========

A ``endaq.device`` "Hello World":

.. code-block:: python

   >>> import endaq.device
   >>> endaq.device.getDevices()
   [<EndaqS S3-E25D40 "Example S3" SN:S0009468 (D:\)>]
   >>> dev = _[0]
   >>> dev.channels
   {8: <Channel 8 '25g PE Acceleration': Acceleration (g)>, 80: <Channel 80 '40g DC Acceleration': Acceleration (g)>, 36: <Channel 36 'Pressure/Temperature': Pressure (Pa), Temperature (°C)>, 65: <Channel 65 'Absolute Orientation': Quaternion (q)>, 70: <Channel 70 'Relative Orientation': Quaternion (q)>, 47: <Channel 47 'Rotation': Rotation (dps)>, 59: <Channel 59 'Control Pad Pressure/Temperature/Humidity': Pressure (Pa), Temperature (°C), Relative Humidity (RH)>, 76: <Channel 76 'Light Sensor': Light (Ill), Light (Index)>}

Configuration Interface
-----------------------
Access to a device's configuration is done through its `config` property.
TODO: Configuration Interface docs

Command Interface
-----------------
Commands can be sent to a device via its `command` property.
TODO: Command Interface docs
