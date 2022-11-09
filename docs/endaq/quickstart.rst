===============================================
``endaq.device`` Concepts and Quick Start Guide
===============================================

.. note::
  This documentation is in very early development.

Basic usage
===========

Finding attached devices
------------------------

A ``endaq.device`` "Hello World":

.. code-block:: python

   >>> import endaq.device
   >>> endaq.device.getDevices()
   [<EndaqS S3-E25D40 "Example S3" SN:S0009468 (D:\)>]
   >>> dev = _[0]
   >>> dev.channels
   {8: <Channel 8 '25g PE Acceleration': Acceleration (g)>, 80: <Channel 80 '40g DC Acceleration': Acceleration (g)>, 36: <Channel 36 'Pressure/Temperature': Pressure (Pa), Temperature (°C)>, 65: <Channel 65 'Absolute Orientation': Quaternion (q)>, 70: <Channel 70 'Relative Orientation': Quaternion (q)>, 47: <Channel 47 'Rotation': Rotation (dps)>, 59: <Channel 59 'Control Pad Pressure/Temperature/Humidity': Pressure (Pa), Temperature (°C), Relative Humidity (RH)>, 76: <Channel 76 'Light Sensor': Light (Ill), Light (Index)>}

Virtual devices
---------------
An enDAQ ``.IDE`` recording file can be used to create a 'virtual' version
of the recorder that created it. This provides an easy way to retrieve
information about the device and how it was configured.

.. code-block:: python

  >>> from idelib.importer import openFile
  >>> with openFile('test.ide') as doc:
  ...     virtual_dev = endaq.device.fromRecording(doc)

Accessing basic recorder properties
===================================
Some `endaq.device.Recorder` properties are identical to those of an
`idelib.Dataset` (an imported recording file). These include:

* ``sensors``: The device's sensors, a dictionary of `idelib.Sensor` objects.
* ``channels``: The device's Channels, a dictionary of `idelib.Channel` objects.
* ``transforms``: The device's data conversion and calibration polynomials, as `idelib.transforms.Transform` objects.

