==========================
Special Topics and How-Tos
==========================

Including ``endaq.device`` in a PyInstaller application
--------------------------------------------------------

``endaq.device`` contains several data files and indirectly imported modules. `PyInstaller <https://pyinstaller.org/en/stable/>`_
does not automatically include these in packaged applications.

* *EBML Schemata:* These XML files describe the format of internal data. ``endaq.device`` has four, and
  `idelib <https://mide-technology-idelib.readthedocs-hosted.com/en/feature-update-docs/>`_
  (one of the package's requirements) has one that must also be included.
* *Default Configuration UI Data:* These Python submodules are used when working with old devices and 'virtual' devices
  generated from IDE files. These submodules are dynamically imported, so PyInstaller does not 'see' them, leaving
  them excluded from the packaged application.

Embedding the schemata and UI descriptions requires small changes to both your main Python file and to the
PyInstaller ``.spec`` file.


Python Changes
^^^^^^^^^^^^^^

Early in one of your first modules to run (e.g., ``your_app.py``), include something like the following:

.. code-block:: python

    import os.path
    import sys

    # First, import `endaq.device` and `idelib`, and `ebmlite`, even if this
    # specific module doesn't need them). Only import them; do not use them yet!
    # Importing them will modify `ebmlite.SCHEMA_PATH`, and we want our changes
    # for PyInstaller use to apply last. For example:
    import endaq.device
    import idelib

    import ebmlite

    # `sys._MEIPASS` only exists in PyInstaller-built packages, and is the path
    # of the executable. Included data directories will be relative to it.
    APP_PATH = os.path.abspath(getattr(sys, '_MEIPASS', os.path.dirname(__file__)))

    # Make the project's schema path the first one searched. This directory
    # doesn't actually need to exist in your project outside of PyInstaller;
    # changes to your `.spec` file will create it in your executable.
    ebmlite.SCHEMA_PATH.insert(0, os.path.join(APP_PATH, 'schemata'))

``.spec`` Changes
^^^^^^^^^^^^^^^^^

You should use PyInstaller with a `.spec <https://pyinstaller.org/en/v4.0/spec-files.html>`_ file,
as some of the tricks for embedding the necessary files can't be done purely via the command line.

Below shows the changes to make to a ``.spec`` file. It is *not* a complete ``.spec`` file.

.. code-block:: python

    from PyInstaller.utils.hooks import collect_submodules

    # Load all the schemata used by your project and its dependencies.
    # Note: Curly brackets denote paths relative to their libraries; they are
    # *not* f-strings. These are required verbatim.
    import ebmlite
    ebmlite.loadSchema("{idelib}/schemata/mide_ide.xml")
    ebmlite.loadSchema("{endaq.device}/schemata/command-response.xml")
    ebmlite.loadSchema("{endaq.device}/schemata/mide_config_ui.xml")
    ebmlite.loadSchema("{endaq.device}/schemata/mide_manifest.xml")

    # Collect the schemata filenames and their path in the executable.
    schemata = [(s.filename, './schemata') for s in ebmlite.SCHEMATA.values()]

    # Collect the 'hidden' Configuration UI submodules.
    hidden = collect_submodules('endaq.device.ui_defaults')

    # Elsewhere in the .spec, there should exist a call to `Analysis()`. Change
    # (or add) the `datas=` and `hiddenimports=` lines shown below.
    a = Analysis(...,
                 datas=schemata,  # <-- Include schemata here!
                 hiddenimports=hidden,  # <-- Include the hidden imports here!
                 ...)
