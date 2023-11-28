######################
The ``Recorder`` Class
######################
.. default-domain:: py
.. currentmodule:: endaq.device

:class:`~.Recorder` is the class representing an enDAQ recording device.
There are several subclasses (:class:`~.endaq.EndaqS`, :class:`~.endaq.EndaqW`,
and legacy :class:`~.slamstick.SlamStickX`,  :class:`~.slamstick.SlamStickC`,
and  :class:`~.slamstick.SlamStickS`), but nearly all functionality is
implemented in :class:`~.Recorder`. Devices that do not have a specific
subclass associated with their product name will instantiate as :class:`~.Recorder`.

.. note::
  Some or all of the discrete product-specific subclasses may be deprecated in the near
  future (the legacy SlamStick classes excluded). Using `isinstance()` to determine
  :class:`~.Recorder` subclasses is not recommended; consider using the properties
  :attr:`~.Recorder.partNumber` and :attr:`~.Recorder.productName` instead
  (see below).

.. autoclass:: endaq.device.base.Recorder
  :members:
