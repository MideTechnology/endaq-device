"""
Import and export of configuration data.

Note: User calibration and Wi-Fi setting are *not* included in the standard
import or export of configuration data. Calibration is specific to one
device, and for security reasons, Wi-Fi settings cannot be extracted from
the device.
"""

__all__ = ('exportConfig', 'importConfig')

from pathlib import Path
from typing import Union

from ebmlite import loadSchema, MasterElement

from .base import Recorder
from .util import cleanProps


def deviceFromExport(export: Union[str, Path, MasterElement]) -> Recorder:
    """ Create a minimal virtual `Recorder` from exported config data. This
        virtual `Recorder` will have only the data relevant to configuration:
        no channels, sensors, calibration, et cetera.

        :param export: The name of an exported config file (``.xcg``), or
            EBML data containing an ``ExportedConfigurationData`` element.
        :return: A minimal 'virtual' `Recorder` instance.
    """
    if isinstance(export, (Path, str)):
        with open(export, 'rb') as f:
            export = loadSchema('mide_ide.xml').loads(f.read())

    if export[0].name == "ExportedConfigurationData":
        export = export[0]

    dev = Recorder(None)
    dev._source = export

    for el in export:
        if el.name == "RecorderConfigurationList":
            dev._config = el
        elif el.name == "RecordingProperties":
            dev._info = el.dump()['RecorderInfo']
        elif el.name == "ConfigUI":
            dev._configUi = loadSchema('mide_config_ui.xml').loads(el.value)

    return dev


def exportConfig(device: Recorder, filename: Union[str, Path]) -> dict:
    """ Generate a configuration export file (``.xcg``). Writes the device's
        current information and configuration data by default.

        Note: User calibration and Wi-Fi setting are *not* included in
        exported configuration data. Calibration is specific to one
        device, and for security reasons, Wi-Fi settings cannot be
        extracted from the device.

        :param device: The device from which to export the config.
        :param filename: The name of the file to write.
    """
    configUi = device.config.getConfigUI()
    config = device.config.getConfig().dump()
    props = device.getProperties()

    # Get contents; the outer element is added on encoding.
    config = config.get('RecorderConfigurationList', config)
    props = props.get('RecordingProperties', props)

    # Encode and write
    data = {'RecorderConfigurationList': config,
            'RecordingProperties': cleanProps(props),
            'ConfigUI': configUi.getRaw()}

    with open(filename, 'wb') as f:
        loadSchema('mide_ide.xml').encode(f, {'ExportedConfigurationData': data})

    return data


def importConfig(device: Recorder,
                 filename: Union[str, Path],
                 merge: bool = False):
    """ Import configuration data from a ``.xcg`` file.

        Note: User calibration and Wi-Fi setting are *not* included in
        imported configuration data. Calibration is specific to one
        device, and for security reasons, Wi-Fi settings cannot be
        extracted from the device.

        :param device: The device to which to import the configuration data.
        :param filename: The name of an exported config file (``.xcg``).
        :param merge: If `True`, keep any device config values not
            explicitly set in the imported configuration data.
        :return:
    """
    imported = deviceFromExport(filename)
    for configId, item in device.config.items.items():
        if configId in imported.config.items:
            item.value = imported.config.items[configId].value
        elif not merge:
            item.value = None
