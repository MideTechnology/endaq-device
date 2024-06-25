"""
Import and export of configuration data.

Note: User calibration and Wi-Fi setting are *not* included in the standard
import or export of configuration data. Calibration is specific to one
device, and for security reasons, Wi-Fi settings cannot be extracted from
the device.
"""

__all__ = ('exportConfig', 'importConfig')

from pathlib import Path
from typing import List, Optional, Union

from ebmlite import loadSchema, MasterElement

from .base import Recorder
from .exceptions import ConfigError
from .util import cleanProps


def deviceFromExport(export: Union[str, Path, MasterElement]) -> Recorder:
    """ Create a minimal virtual `Recorder` from exported config data. This
        virtual `Recorder` will have only the data relevant to configuration:
        no channels, sensors, calibration, et cetera.

        :param export: The name of an exported config file (``.xcg``), or
            EBML data containing an ``ExportedConfigurationData`` element.
        :return: A minimal 'virtual' `Recorder` instance.
    """
    if not isinstance(export, MasterElement):
        with open(export, 'rb') as f:
            export = loadSchema('mide_ide.xml').loads(f.read())

    if export[0].name == "ExportedConfigurationData":
        export = export[0]

    configData = None
    rawinfo = None
    configUi = None

    for el in export:
        if el.name == "RecorderConfigurationList":
            configData = el
        elif el.name == "RecordingProperties":
            rawinfo = el.getRaw()
        elif el.name == "ConfigUI":
            configUi = loadSchema('mide_config_ui.xml').loads(el.value)

    dev = Recorder(None, virtual=True, devinfo=rawinfo)
    dev._devinfo = None
    dev._source = export
    dev._configUi = configUi
    dev._configData = configData
    dev.getInfo()

    return dev


def exportConfig(device: Recorder,
                 filename: Union[str, Path],
                 unknown: bool = False,
                 defaults: bool = False) -> dict:
    """ Generate a configuration export file (``.xcg``). Writes the device's
        current information and configuration data by default.

        Note: User calibration and Wi-Fi setting are *not* included in
        exported configuration data. Calibration is specific to one
        device, and for security reasons, Wi-Fi settings cannot be
        extracted from the device.

        :param device: The device from which to export the config.
        :param filename: The name of the file to write.
        :param unknown: If `True`, include values read from the config
            file that did not correspond to known configuration items.
        :param defaults: If `True`, include config values that have not
            been explicitly set (i.e. still their default value).
    """
    config = device.config._makeConfig(unknown=unknown, defaults=defaults)
    configUi = device.config.getConfigUI()
    props = {'RecorderInfo': device.getInfo()}

    # Get contents; the outer element is added on encoding.
    config = config.get('RecorderConfigurationList', config)

    # Encode and write
    data = {'RecorderConfigurationList': config,
            'RecordingProperties': cleanProps(props),
            'ConfigUI': configUi.getRaw()}

    with open(filename, 'wb') as f:
        loadSchema('mide_ide.xml').encode(f, {'ExportedConfigurationData': data})

    return data


def importConfig(device: Recorder,
                 filename: Union[str, Path],
                 merge: bool = False,
                 exclude: Optional[List[int]] = None):
    """ Import configuration data from a ``.xcg`` file.

        Note: User calibration and Wi-Fi setting are *not* included in
        imported configuration data. Calibration is specific to one
        device, and for security reasons, Wi-Fi settings cannot be
        extracted from the device.

        :param device: The device to which to import the configuration data.
        :param filename: The name of an exported config file (``.xcg``).
        :param merge: If `True`, keep any device config values not
            explicitly set in the imported configuration data.
        :param exclude: An optional list of configuration IDs to ignore.
            These will neither be imported from the file, nor set to default
            if `merge` is `True`.
        :return:
    """
    exclude = tuple() if exclude is None else exclude
    imported = deviceFromExport(filename)
    for configId, item in device.config.items.items():
        if configId in exclude:
            continue
        if configId in imported.config.items:
            item.value = imported.config.items[configId].value
        elif not merge:
            item.value = None
