================
``endaq.device``
================

.. note::
  This documentation is in very early development.

``endaq.device`` provides a means of representing, accessing, configuring and controlling
`enDAQ™ data recorders <https://endaq.com/collections/endaq-shock-recorders-vibration-data-logger-sensors>`_. It
also supports legacy SlamStick™ devices (X, C, and S).

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   endaq/quickstart
   endaq/config_control
   endaq/special_topics
   api_ref


Installation
------------
The ``endaq-device`` package is `available on PyPI <https://pypi.org/project/endaq-device/>`_, and can be installed via `pip`::

    pip install endaq-device

For the most recent features that are still under development, you can also use `pip` to install endaq directly from `the GitHub repository <https://github.com/MideTechnology/endaq-device/>`_::

    pip install git+https://github.com/MideTechnology/endaq-device.git@development

Note: While ``endaq-device`` installs into the same ``endaq`` 'namespace' as `endaq-python <https://docs.endaq.com/en/latest/index.html>`_,
it is otherwise separate; the two packages are not interdependent, and one can be installed without the other.
The packages do distinctly different things, and have very different use-cases.


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
