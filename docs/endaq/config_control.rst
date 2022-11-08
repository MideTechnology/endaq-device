####################################
Configuration and Control Interfaces
####################################
.. default-domain:: py
.. currentmodule:: endaq.device

Device configuration and control is done through 'interfaces,' objects that encapsulate the
processes. Typically, neither of these interfaces are explicitly created; accessing
:attr:`Recorder.config` and :attr:`Recorder.command` will automatically instantiate a
:class:`~.config.ConfigInterface` or :class:`~.command_interfaces.CommandInterface` subclass
appropriate for the given device.

There is some overlap between the configuration and command interfaces; for example, configuring
Wi-Fi or setting a device's clock are handled through the command interface. As a rule, changes
that happen immediately are commands, and changes that apply after the recorder restarts
(e.g., being reset, starting a recording, being disconnected) are handled by the configuration
interface.

Configuration
-------------
.. autoclass:: endaq.device.config.ConfigInterface
  :members:

Control
-------
.. autoclass:: endaq.device.command_interfaces.CommandInterface
  :members:
