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
=============
.. autoclass:: endaq.device.config.ConfigInterface
  :members:

Control
=======
.. autoclass:: endaq.device.command_interfaces.CommandInterface
  :members:

Special Notes
=============

Callback Functions
------------------
Several commands feature a parameter for a *callback function*, which will be
called periodically during potentially long-running functions. Callbacks are
primarily intended for use with GUIs. If the function returns `True`, the
command will be cancelled. Also, in cases in which the command is executing
in the foreground thread, the callback creates an opportunity to update the UI.

Callback functions require no arguments, but for the sake of future-proofing,
it is recommended that the functions accept them. In the future, commands may
provide information via arguments (e.g., the percentage completed, elapsed
time, etc.).

.. code-block:: python

    def my_callback(*args, **kwargs):
        """ Fake example callback function. Accepts any positional or keyword arguments,
            but ignores them. Setting the global variable `keep_going` to `True` will
            make the function return `True`, cancelling the command to which the callback
            function was provided.
        """
        # Something could happen here, like yielding some cycles to the GUI.
        # ...
        if keep_going:
            return False
        else:
            return True
