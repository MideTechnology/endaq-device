"""
Conversion between legacy (pre EFM32 GG0 FWRev 15) and contemporary config
file formats. These get used automatically for older SlamStick devices.
"""

__author__ = "dstokes"
__copyright__ = "Copyright 2023 Mide Technology Corporation"

from typing import Any, AnyStr, Dict, TYPE_CHECKING, Union

from ebmlite import loadSchema, Document, MasterElement

import logging
logger = logging.getLogger('endaq.device.legacy')

from .measurement import ACCELERATION

if TYPE_CHECKING:
    from .base import Recorder
    from .config import ConfigInterface

# ==============================================================================
#
# ==============================================================================


def _copyItems(oldD: AnyStr, newD: AnyStr, *keyPairs):
    """ Utility function to copy existing, non-`None` items from one dictionary
        to another, using different keys.
    """
    for oldK, newK in keyPairs:
        val = oldD.get(oldK)
        if val is not None and val != "":
            newD[newK] = val


def convertConfigItems(config: dict,
                       device: "Recorder") -> Dict[int, Any]:
    """ Convert legacy-style ``RecorderConfiguration`` items to the
        new ``RecorderConfigurationList`` style.

        :param config: A dictionary, dumped from an EBML
            ``RecorderConfiguration`` element.
        :param device: The device containing the data.
        :return: A dictionary of ConfigIDs and values (the 'new' format).
    """
    if not config:
        return {}

    newData = {}
    channels = device.getChannels()

    if 'RecorderConfiguration' in config:
        config = config['RecorderConfiguration']

    # Combine 'root' dictionaries for easy access
    basicConfig = config.get('SSXBasicRecorderConfiguration', {})
    userConfig = config.get('RecorderUserData', {})
    triggerConfig = config.get('SSXTriggerConfiguration', {})
    channelConfig = config.get('SSXChannelConfiguration', [])

    # Basic stuff. Items only added if they exist in the old config data.
    _copyItems(basicConfig, newData,
               ('SampleFreq', 0x02ff08),
               ('AAFilterCornerFreq', 0x08ff08),
               ('PlugPolicy', 0x0aff7f),
               ('UTCOffset', 0x0bff7f))

    _copyItems(userConfig, newData,
               ('RecorderName', 0x08ff7f),
               ('RecorderDesc', 0x09ff7f))

    _copyItems(triggerConfig, newData,
               ('WakeTimeUTC', 0x0fff7f),
               ('PreRecordDelay', 0x0cff7f),
               ('RecordingTime', 0x0dff7f),
               ('AutoRearm', 0x0eff7f))

    # Channel configuration.
    for ch in channelConfig:
        chId = ch.get('ConfigChannel')
        enables = ch.get('SubChannelEnableMap', 0xFF)
        sampFreq = ch.get('ChannelSampleFreq')

        if chId is None:
            continue
        if enables is not None:
            newData[0x01FF00 | (chId & 0xFF)] = enables
        if sampFreq is not None:
            newData[0x02FF00 | (chId & 0xFF)] = sampFreq

    # Trigger configuration.
    dcAccelMap = 0  # For building DC accelerometer's 'participation map'.

    for trigger in triggerConfig.get('Trigger', []):
        chId = trigger.get('TriggerChannel')
        subchId = trigger.get('TriggerSubChannel', 0xff) & 0xff
        trigLo = trigger.get('TriggerWindowLo')
        trigHi = trigger.get('TriggerWindowHi')

        if chId is None:
            continue

        if chId not in channels:
            # Convert very early firmware channel IDs
            if chId == 0 and 8 in channels:
                chId = 8
            elif chId == 1 and 36 in channels:
                chId = 36
            else:
                logger.warning("Ignoring bad trigger channel ID: %r" % chId)
                continue

        combinedId = (subchId << 8) | (chId & 0xFF)

        if chId == 32:
            # Special case: DC accelerometer (new data uses 'participation map'
            # instead of individual subchannel triggers).
            dcAccelMap |= (1 << subchId)
            combinedId = combinedId | 0x00FF00
        else:
            newData[0x050000 | combinedId] = 1

        if trigLo is not None:
            newData[0x030000 | combinedId] = trigLo
        if trigHi is not None:
            newData[0x040000 | combinedId] = trigHi

    if dcAccelMap > 0:
        newData[0x05FF20] = dcAccelMap

    accels = device.getChannels(ACCELERATION)
    analogChannel = accels.get(8, accels.get(0, None))

    if analogChannel:
        enableId = 0x01ff00 | (analogChannel.id & 0xFF)
        if enableId not in newData:
            newData[enableId] = 0
            for _ch in analogChannel.subchannels:
                newData[enableId] = (newData[enableId] << 1) | 1

    return newData


def convertConfigFile(original: Union[Document, MasterElement],
                      interface: "ConfigInterface") -> MasterElement:
    """ Convert legacy-style ``RecorderConfiguration`` data to the
        new ``RecorderConfigurationList`` style.

        :param original: The original, legacy format EBML config document.
        :param interface: The `ConfigInterface` requesting the conversion.
        :return: An EBML config document in the new format.
    """
    vals = convertConfigItems(original.dump(), interface.device)

    data = []
    items = {'RecorderConfigurationItem': data}

    for k, v in vals.items():
        if k in interface._items:
            data.append({'ConfigID': k,
                         interface._items[k].vtype: v})

    schema = loadSchema('mide_ide.xml')
    ebml = schema.encodes({'RecorderConfigurationList': items},
                          headers=False)
    return schema.loads(ebml)


def generateLegacyConfig(configData: dict, device: "Recorder") -> dict:
    """ Build an EBML-encodable set of nested dictionaries containing the
        dialog's configuration values in the legacy format. Note: the
        `configData` should not contain any `None` values; these will be
        ignored.

        :param configData: A dictionary of configuration data, in the new
            style (flat, keyed by ConfigID).
        :param device: The device to which to write.
    """
    # Copy the data, just in case.
    configData = configData.copy()

    # Individual dictionaries/lists for each section of the old config
    userConfig = {}
    basicConfig = {}
    triggerConfig = {}
    channelConfig = []

    # Basic stuff. Items only added if they exist in the new config data.
    _copyItems(configData, userConfig,
               (0x08ff7f, 'RecorderName'),
               (0x09ff7f, 'RecorderDesc'))

    _copyItems(configData, basicConfig,
               (0x02ff08, 'SampleFreq'),
               (0x08ff08, 'AAFilterCornerFreq'),
               (0x0aff7f, 'PlugPolicy'),
               (0x0bff7f, 'UTCOffset'))

    _copyItems(configData, triggerConfig,
               (0x0fff7f, 'WakeTimeUTC'),
               (0x0cff7f, 'PreRecordDelay'),
               (0x0dff7f, 'RecordingTime'),
               (0x0eff7f, 'AutoRearm'))

    # Trigger configuration: separate master elements for each subchannel.
    triggers = []

    # Get all trigger enables/subchannel participation maps
    for t in [k for k in configData if (k & 0xFF0000 == 0x050000)]:
        combinedId = t & 0x00FFFF
        trigLo = configData.get(0x030000 | combinedId)
        trigHi = configData.get(0x040000 | combinedId)

        trig = {'TriggerChannel': combinedId & 0xFF}

        # Special case: DC accelerometer, which uses a 'participation' bitmap
        # instead of having explicit ConfigID items for each subchannel. In
        # legacy data, each subchannel has its own trigger element, with the
        # same threshold value in each (can't change per subchannel).
        if t == 0x05FF20:
            v = configData[0x05FF20]
            trigHi = configData.get(0x04ff20)
            if trigHi is not None:
                trig['TriggerWindowHi'] = trigHi
            for i in range(3):
                if (v >> i) & 1:
                    d = trig.copy()
                    d['TriggerSubChannel'] = i
                    triggers.append(d)
        else:
            trig['TriggerSubChannel'] = ((combinedId & 0x00FF00) >> 8)
            triggers.append(trig)

        if trigLo is not None:
            trig['TriggerWindowLo'] = trigLo
        if trigHi is not None:
            trig['TriggerWindowHi'] = trigHi

    if triggers:
        triggerConfig['Trigger'] = triggers

    # Channel configuration: per-axis enables, sample rate for some.
    for c in device.getChannels():
        combinedId = 0xFF00 | (c & 0xFF)
        d = {}
        _copyItems(configData, d,
                   (0x020000 | combinedId, "ChannelSampleFreq"),
                   (0x010000 | combinedId, "SubChannelEnableMap"))

        # Only save if something's been set.
        if d:
            d['ConfigChannel'] = c
            channelConfig.append(d)

    # Build the complete old-style configuration dictionary. Only add stuff
    # with content.
    legacyConfigData = {}

    if basicConfig:
        legacyConfigData['SSXBasicRecorderConfiguration'] = basicConfig
    if userConfig:
        legacyConfigData['RecorderUserData'] = userConfig
    if triggerConfig:
        legacyConfigData['SSXTriggerConfiguration'] = triggerConfig
    if channelConfig:
        legacyConfigData['SSXChannelConfiguration'] = channelConfig

    return {'RecorderConfiguration': legacyConfigData}
