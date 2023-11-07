"""
Interfaces for configuring enDAQ recorders.

Note: Wi-Fi configuration is done through the command interface. Changes
though the configuration interface are applied when the device next
resets or starts recording, while Wi-Fi changes take effect immediately.
This also keeps Wi-Fi access point passwords secret. Similarly, setting the
device's realtime clock is also done through the command interface, as it
also takes effect immediately.
"""

import errno
import logging
import os.path
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, TYPE_CHECKING
import warnings

from ebmlite.core import loadSchema
from ebmlite.core import Document, Element, MasterElement
from idelib.dataset import Channel, SubChannel

from .exceptions import ConfigError, UnsupportedFeature
from . import legacy
from . import ui_defaults
from . import util

if TYPE_CHECKING:
    from .base import Recorder

logger = logging.getLogger('endaq.device')


# ===========================================================================
#
# ===========================================================================

class ConfigItem:
    """ A single configuration item/field, read from Config UI data, e.g., a
        device's ``CONFIG.UI`` file. It keeps track of the item's data type
        and handles conversion between internal and real-world units where
        applicable. It can also perform basic validation (minimum, maximum,
        specific valid options, etc.) if the ``CONFIG.UI`` data provides the
        required information.
    """

    # Mapping of field element names (exact match) to object attributes.
    ARGS = {"Label": "label",
            "ToolTip": "tooltip",
            "Units": "units",
            "DisplayFormat": "displayFormat",
            "ValueFormat": "valueFormat",
            "MaxLength": "maxLength",
            "EnumOption": "options"}

    # Mapping of *Field EBML IDs last 4 bits to value types.
    # For generating a default `vtype` for fields w/o a default *Value.
    TYPES = {0x00: "BooleanValue",
             0x01: "UIntValue",
             0x02: "IntValue",
             0x03: "FloatValue",
             0x04: "ASCIIValue",
             0x05: "TextValue",
             0x06: "BinaryValue",
             0x07: "UIntValue",  # enum, bitfield
             0x08: "BooleanValue"}  # group (e.g. a CheckGroup)

    # The low nybble of *Field EBML IDs represents their data type.
    DTYPES = {0x0: bool,
              0x1: int,
              0x2: int,
              0x3: float,
              0x4: str,
              0x5: str,
              0x6: bytes}

    # Names for configuration item types based on the high 8 bits of the
    # ConfigID, for generating labels for *Fields without Label elements
    TYPE_LABELS = {0x010000: 'Enable',
                   0x020000: 'Sample Rate',
                   0x030000: 'Low Trigger',
                   0x040000: 'High Trigger',
                   0x050000: 'Trigger Enable'}

    # Labels and tool tip strings for standard *Fields (usually special types)
    # that don't have `Label` and/or `ToolTip` elements.
    DEFAULT_LABELS = {
        0x0bff7f: ('UTC Offset', "The local timezone's offset from UTC time.")
    }

    # Default expression code objects for ValueFormat and DisplayFormat.
    # `noEffect` always returns the field's value unmodified (supplied as the
    # variable ``x``).
    noEffect = compile("x", "<ConfigItem.noEffect>", "eval")


    _tagsDisplay = compile("[t.strip() for t in x.split(',')]",
                           "<ConfigItem._tagDisplay>", "eval")

    _tagsValue = compile("','.join(str(x).strip()) if x else ''",
                         "<ConfigItem._tagValue>", "eval")

    @classmethod
    def _generateLabel(cls, configId: int) -> Union[str, None]:
        """ Helper method to create a 'label' string from a ConfigID (using
            the standard conventions) if the \\*Field element does not contain
            one. Mainly works for standard channel/subchannel-specific fields.
        """
        if configId in cls.DEFAULT_LABELS:
            return cls.DEFAULT_LABELS[configId][0]

        subch = (configId >> 8) & 0xFF
        ch = configId & 0xFF

        t = configId & 0xFF0000
        label = cls.TYPE_LABELS.get(t, None)

        if label is None:
            if ch == 0x7f:
                # Device-wide config item, no label
                return None
            # Config item type unknown
            label = "ConfigID 0x{:06x}".format(configId)

        if subch != 0xff:
            return "SubChannel {}.{} {}".format(ch, subch, label)
        return "Channel {} {}".format(ch, label)


    def __init__(self,
                 interface,
                 element: MasterElement,
                 data: Optional[dict] = None,
                 value: Optional[Any] = None):
        """
        `ConfigItem` is rarely (if ever) explicitly instantiated; instances
        are automatically created by a `ConfigInterface`, using CONFIG.UI
        data.

        :param interface: The 'parent' `ConfigInterface`.
        :param element: The raw CONFIG.UI `*Field` EBML element.
        :param data: The `element` contents, dumped as a dictionary. Avoids
            redundant dumping.
        :param value: The raw value (in native units) as read from a config
            file.
        """
        if data is None:
            data = element.dump()
        self.configId = data['ConfigID']

        # These attributes don't appear in ARGS
        self.interface = interface
        self.element = element
        self._default = None  # field default, in internal units
        self.vtype = None  # Type of *Value element in config data
        self.dtype = self.DTYPES.get(element.id & 0x0F, None)  # Value's Python data type

        # Internal/engineering unit conversion
        self.displayFormat = self.valueFormat = None
        self.gain = self.offset = None

        # Validation
        self.min = float('-inf')
        self.max = float('inf')
        self.maxLength = float('inf')
        self.options = []

        # For future use (if any)
        self.label = self.tooltip = self.units = None

        for k, v in data.items():
            if k in self.ARGS:
                setattr(self, self.ARGS[k], v)
            elif k.endswith('Value'):
                # Config item type determined by *Value element type
                # (if present; fallback behaviors below)
                self.vtype, self._default = k, v
            else:
                # Elements with data type as prefix
                for attr in ("Min", "Max", "Gain", "Offset"):
                    if k.endswith(attr):
                        setattr(self, attr.lower(), v)

        if self.options:
            # Choices for an EnumField or BitField
            self.options = self.parseOptions(self.options)

        if self.vtype is None:
            # No default *Value, and no type in an EnumOption;
            # fall back to type encoded in *Field EBML ID
            self.vtype = self.TYPES.get(self.element.id & 0x0f, None)

        if self.dtype is None and interface and self.vtype:
            # Data type not in dictionary of types (probably an *Enum);
            # get type from *Value element
            self.dtype = interface._schema[self.vtype].dtype

        if self.gain or self.offset:
            self.makeGainOffsetFormat()
        else:
            self._displayFormat = self.makeExpression(self.displayFormat, "displayFormat")
            self._valueFormat = self.makeExpression(self.valueFormat, "valueFormat")

        if not self.label:
            self.label = self._generateLabel(self.configId)

        if not self.tooltip:
            self.tooltip = self.DEFAULT_LABELS.get(self.configId, ('', ''))[1]

        self.configValue = value

        self._fromFile = None  # Indicates value was read from file, set during load
        self._changed = False  # Overrides item value change detection
        self._originalValue = self.value  # Part of change detection


    def parseOptions(self, options: list) -> dict:
        """ Parse a list of `<EnumOption>` elements into a list of value
            choices. Note: also sets `vtype` if not already set by the
            default *Value element.
        """
        parsedoptions = {}
        for n, option in enumerate(options):
            # EnumOption values default to their index in the list
            value = 1 << n if self.element.name.endswith('BitField') else n
            for k, v in option.items():
                if k.endswith('Value'):
                    value = v
                    if self.vtype is None:
                        self.vtype = k
            parsedoptions[value] = option.get('Label', None)
        return parsedoptions


    def makeExpression(self, exp: Optional[str], name: str = ""):
        """ Helper method for compiling an expression in a string into a code
            object that can later be used with `eval()`. Used internally.

            :param exp: The conversion function, as a Python string.
            :param name: The name of the expression (i.e., "displayFormat" or
                "valueFormat"), embedded in the resulting code object. Mostly
                for debugging.
        """
        if exp is None:
            # No expression defined: value is returned unmodified (it matches
            # the config item's type)
            return self.noEffect
        elif exp == '':
            # Expression element exists, but empty: Config item generates no
            # output. Usually for GUI interactivity (disabling one widget
            # based on another, like CheckGroups).
            return None

        # Create a nicely formatted, informative string for the compiled
        # expression's "filename" and for display if the expression is bad.
        idstr = "(ID 0x{:02x}) ".format(self.configId) if self.configId else ""
        msg = "{}{}".format(idstr, name)

        if not isinstance(exp, str):
            # Probably won't occur, but just in case...
            logger.debug("Ignoring bad value for {}: {!r} ({})".format(idstr, exp, type(exp)))
            return

        try:
            return compile(exp, "<{}>".format(msg), "eval")
        except SyntaxError as err:
            logger.error("Ignoring bad expression for {}: {!r}".format(msg, err))
            return self.noEffect


    def makeGainOffsetFormat(self):
        """ Helper method for generating `displayFormat` and `valueFormat`
            expressions using the field's `gain` and `offset`. Used internally.
        """
        gain = 1.0 if self.gain is None else self.gain
        offset = 0.0 if self.offset is None else self.offset

        self.displayFormat = "(x + {:.8f}) * {:.8f}".format(offset, gain)
        self.valueFormat = "x / {:.8f} - {:.8f}".format(gain, offset)

        self._displayFormat = self.makeExpression(self.displayFormat, "displayFormat")
        self._valueFormat = self.makeExpression(self.valueFormat, "valueFormat")


    def __repr__(self):
        msg = "{} ID 0x{:06x}".format(type(self).__name__, self.configId)
        if self.label:
            msg = "{}: {!r}".format(msg, self.label)
        if self.dtype:
            dtype = self.dtype.__name__
            bits = "Bit" in self.element.name
            if self._value is not None:
                val = bin(self._value) if bits else repr(self._value)
                changed = "" if self._value == self._originalValue else "*"
                msg = "{} ({}={}){}".format(msg, dtype, val, changed)
            else:
                msg = "{} ({})".format(msg, dtype)
        return "<{}>".format(msg)


    @property
    def value(self) -> Any:
        """ The configuration item value, in standard engineering units (Pa,
            g, degrees, etc.) where applicable. """
        return self._value


    @value.setter
    def value(self, v: Any):
        """ Set the configuration item value, in engineering units (Pa,
            g, degrees, etc.) where applicable.
        """
        if v is None or (self.interface and not self.interface.validate):
            self._value = v
            return

        if self.element.name.endswith('EnumField') and self.options and v not in self.options:
            raise ValueError("Invalid value for {}, must be one of {}"
                             .format(self, tuple(self.options)))
        elif isinstance(v, str) and len(v) > self.maxLength:
            raise ValueError("Invalid value for {}, max string length is {}"
                             .format(self, self.maxLength))
        elif isinstance(v, (int, float)) and not self.min <= v <= self.max:
            if self.min == float('-inf'):
                msg = "<= {}".format(self.max)
            elif self.max == float('inf'):
                msg = ">= {}".format(self.min)
            else:
                msg = "{} <= v <= {}".format(self.min, self.max)
            raise ValueError("Invalid value for {}, must be {}"
                             .format(self, msg))
        else:
            self._value = v


    @property
    def configValue(self) -> Any:
        """ The item's value, in the config file's native units. """
        # Null string valueFormat
        if self._value is None or self.valueFormat == '':
            return None
        return eval(self._valueFormat, {'x': self._value})


    @configValue.setter
    def configValue(self, v: Any):
        """ Set the item's value using the config file's native units. """
        if v is None:
            self._value = v
        else:
            self._value = eval(self._displayFormat, {'x': v})


    @property
    def default(self) -> Any:
        """ The configuration item's default value. """
        if self._default:
            return eval(self._valueFormat, {'x': self._default})


    @property
    def changed(self) -> bool:
        """ Has the value of the ConfigItem changed? `True` if the current
            value differs from the previous value. This can also be manually
            set to `True` or `False`, although if set `False`, changing the
            ConfigItem's value afterwards will override it.
        """
        return self._changed or self._value != self._originalValue


    @changed.setter
    def changed(self, changed: bool):
        if not changed:
            self._originalValue = self._value
        self._changed = changed


    def revert(self) -> bool:
        """ Reset the item to the value read from the config file, or `None`
            if the item's value was not from a config file.

            :return: `True` if the value was reverted, `False` if the value was
                unchanged.
        """
        if self.configValue != self._fromFile:
            self.configValue = self._fromFile
            self.changed = False
            return True
        return False


    def dump(self) -> Union[None, dict]:
        """ Generate a dictionary containing the item's config ID and value.
            Used when generating a new config file.

            :return: A 2 item dictionary if `value` is not `None`, else
                `None`.
        """
        if self.value is not None:
            return {'ConfigID': self.configId,
                    self.vtype: self.configValue}
        return None


# ===========================================================================
#
# ===========================================================================

class ConfigInterface:
    """
    Base class for mechanisms to access/modify device configuration.

    :ivar config: Device configuration data (e.g., data read from the config
        file). This may be set manually to override defaults and/or existing
        configuration data. Manual setting must be done after instantiation
        and before accessing config elements via the interface's `item`
        attribute.
    :ivar configUi: Device configuration UI information. May be set manually
        to override defaults. Manual setting must be done after instantiation
        and before accessing config elements via `item`.
    :ivar unknownConfig: A dictionary of configuration item types and values,
        keyed by Config ID. Items read from the configuration file that do
        not match items in the ``ConfigUI`` data go into the dictionary.
        These will (by default) be written back to the config file verbatim.
        `unknownConfig` may also be used to manually add arbitrary items to
        the config file.
    """

    def __init__(self, device: "Recorder"):
        """ `ConfigInterface` instances are rarely (if ever) explicitly
            created; the parent `Recorder` object will create the
            appropriate `ConfigInterface` when its `config` property is
            first accessed.

            :param device: The Recorder to configure.
        """
        self._schema = loadSchema('mide_config_ui.xml')
        self.device: Optional["Recorder"] = device
        self.configUi: Optional[MasterElement] = None
        self.config: Optional[MasterElement] = None
        self._items: Dict[int, ConfigItem] = {}
        self._allitems: Dict[int, ConfigItem] = {}  # for debugging, mostly

        # Config values from the loaded configuration data that don't have
        # a corresponding field in the ConfigUI data. Keyed by ConfigID,
        # values are tuples of (*Value element name, value). This can be
        # modified directly to add new/custom configuration values.
        self.unknownConfig: Dict[int, Tuple[str, Any]] = {}

        # For future use
        self.postConfigMsg = None

        # For disabling validation of item values. Setting to `False` will
        # ignore the item's min/max and options. Primarily for testing.
        self.validate = True

        # The format version of the last config data read.
        self.configVersionRead = None
        self._supportedConfigVersions = None


    @property
    def supportedConfigVersions(self):
        """ A tuple of configuration data format versions supported by
            the interface. 1 is the original SlamStick version, only
            supported on old hardware/firmware. The current version is 2.
        """
        return (2,)


    @property
    def items(self) -> Dict[int, ConfigItem]:
        """ All defined configuration items for the device, keyed by
            Config ID.
        """
        if not self.configUi:
            self._items.clear()
            self._allitems.clear()
            self.configUi = self.getConfigUI()
            self.parseConfigUI(self.configUi)

        if self.config is None:
            try:
                self.loadConfig()
            except Exception as err:
                warnings.warn('Error when reading config file: {!r}'.format(err))

        return self._items


    @items.setter
    def items(self, items: Dict[int, ConfigItem]):
        self._items = items
        self._allitems.update(items)


    @classmethod
    def hasInterface(cls, device: "Recorder") -> bool:
        """ Determine if a device supports this `ConfigInterface` type.

            :param device: The Recorder to check.
            :return: `True` if the device supports the interface.
        """
        if getattr(device, "_config", None) is not None:
            return True
        return ui_defaults.getDefaultConfigUI(device) is not None


    @property
    def available(self) -> bool:
        """ Is the device currently ready for configuration?

            Note: This is intended for future configuration systems. Since
            configuration is currently applied via the filesystem, it is
            functionally the same as `Recorder.available`.
        """
        # For now, this is basically the same as the device availability,
        # but allows for future config interfaces (e.g., remote and/or
        # wireless, etc.)
        return self.device.available


    def parseConfigUI(self,
                      configUi: Union[Document, Element]):
        """ Recursively process CONFIG.UI data to populate the interface's
            dictionaries of configuration items.

            :param configUi: A parsed `CONFIG.UI` EBML document or element.
        """
        for el in configUi:
            if el.name == 'PostConfigMessage':
                self.postConfigMsg = el.value
                continue

            if not isinstance(el, MasterElement):
                continue

            # Note: all MasterElement subclasses have the attribute `name`
            if el.name.endswith("Field") or el.name == 'CheckGroup':
                data = el.dump()
                if 'ConfigID' in data:
                    item = ConfigItem(self, el, data)
                    self._allitems[item.configId] = item

                    # Exclude items that don't generate config file values
                    if item.valueFormat != '':
                        self._items[item.configId] = item

            if el.name in ('ConfigUI', 'Tab') or 'Group' in el.name:
                self.parseConfigUI(el)


    def getChanges(self) -> List[ConfigItem]:
        """ Has the configuration data been modified? """
        # Deliberately check all `changed` (it resets when gotten)
        return [item for item in self.items.values() if item.changed]


    def revert(self):
        """ Reset all configuration values to what was originally read from
            the configuration file, or `None` if the value was never read
            from the file.
        """
        for item in self.items.values():
            if item.revert():
                logger.debug('Reverted {!r}'.format(item))


    def _parseConfig(self,
                     origConfig: dict,
                     default: Optional[dict] = None) -> Union[Dict[int, Any], None]:
        """ Helper method to parse a dictionary of dumped EBML
            ``RecorderConfigurationList`` data into a simple dictionary of
            values keyed by ConfigID. Used internally.

            :param origConfig: The unprocessed dictionary dumped from a
                configuration EBML file.
            :param default: A dictionary of default config values.
        """
        config = {} if default is None else default.copy()

        root = origConfig.get('RecorderConfigurationList', None)
        if root is None:
            return None

        for item in root.get('RecorderConfigurationItem', []):
            configId = item.get('ConfigID', None)
            if not configId:
                continue

            for k, v in item.items():
                if k.endswith('Value') and v is not None:
                    config[configId] = bool(v) if "Boolean" in k else v
                    break

        return config


    def _makeConfig(self,
                    unknown: bool = True,
                    version: Optional[int] = None) -> Dict[str, Any]:
        """ Generate a dictionary of configuration data, suitable for EBML
            encoding.

            Note: this is currently used directly by another project (the
            config GUI's exporter). Be careful modifying until import/export
            has been moved to this package and the config GUI is updated.

            :param unknown: If `True`, include configuration items in the
                `ConfigInterface`'s `unknownConfig`; items read from the
                configuration file but have IDs that do not correspond to
                fields in the device's ``ConfigUI`` data.
            :param version: The version of configuration data to use.
            :return: A dictionary of configuration values, ready for encoding
                as EBML.
        """
        supportedVersions = self.supportedConfigVersions
        if version is not None and version not in supportedVersions:
            raise ConfigError("Device does not support config data version {}, only {}".
                              format(version, supportedVersions))

        config = [item.dump() for item in self.items.values()
                  if item.dump() is not None]
        if unknown:
            for k, v in self.unknownConfig.items():
                config.append({'ConfigID': k, v[0]: v[1]})

        return {'RecorderConfigurationList':
                    {'RecorderConfigurationItem': config}}


    def getConfigUI(self) -> Union[Document, MasterElement]:
        """ Get the device's ``ConfigUI`` data.
        """
        raise NotImplementedError("getConfigUI() not implemented")


    def getConfig(self) -> Union[Document, MasterElement]:
        """ Low-level method that retrieves the device's config EBML (e.g.,
            the contents of a real device's `config.cfg` file), if any.
        """
        raise NotImplementedError("getConfig() not implemented")


    def getConfigValues(self,
                        original: bool = False,
                        defaults: bool = False,
                        none: bool = False,
                        unknown: bool = True) -> Dict[int, Any]:
        """ Get the device configuration as a simple dictionary of values
            keyed by config ID.

            :param original: If `True`, return only the values read from the
                device configuration. Overrides the other parameters.
            :param defaults: If `True`, include items with their default
                values, not only those explicitly set or read from a file.
            :param none: If `False`, exclude items with values of `None`.
            :param unknown: If `True`, include values read from the
                config file that do not correspond to know configuration
                items.
        """
        # TODO: this seems really kludgey. Maybe split into different methods?
        if original:
            if not self.config:
                return {}

            return self._parseConfig(self.config.dump())

        conf = {item.configId: item.value for item in self.items.values()
                if ((defaults or item.configValue != item._default) and
                    (none or item.value is not None))}

        if unknown:
            for k, v in self.unknownConfig.items():
                conf[k] = v[1]

        return conf


    def applyConfig(self,
                    unknown: bool = True,
                    version: Optional[int] = None):
        """ Apply (save) configuration data to the device.

            :param unknown: If `True`, include values that do not correspond
                to known configuration items (e.g., originally read from the
                config file).
            :param version: The version of configuration data to use, if the
                device supports more than one. Defaults to the latest
                version supported.
        """
        raise NotImplementedError("applyConfig() not implemented")


    def saveAs(self,
               filename: Union[str, Path],
               unknown: bool = True,
               version: Optional[int] = None):
        """ Save the raw configuration data to a file (e.g., ``config.cfg``).
            The file saved is the equivalent of the recorder's native config
            data, and can only be applied to the original recorder (or one of
            the same model). To export configuration data for use on another
            device, use `endaq.device.configio.exportConfig()`.

            :param filename: The name of the output file. By convention, the
                extension is ``.cfg``, but this is not enforced.
            :param unknown: If `True`, include values that do not correspond
                to known configuration items (e.g., originally read from the
                config file).
            :param version: The version of configuration data to use, if the
                device supports more than one. Defaults to the latest
                version supported.
        """
        data = self._makeConfig(unknown=unknown, version=version)
        with open(filename, 'wb') as f:
            loadSchema('mide_ide.xml').encode(f, data)


    def loadConfig(self, config: Optional[MasterElement] = None):
        """ Process a device's configuration data.

            :param config: Optional, explicit configuration EBML data to
                process. If none is provided, the data retrieved by
                `getConfig()` will be used.
        """
        if config is None:
            config = self.config or self.getConfig()

        if not config:
            self.config = {}
            return

        dump = config.dump()

        root = dump.get('RecorderConfigurationList', dump)
        if root:
            for item in root.get('RecorderConfigurationItem', []):
                k = item['ConfigID']
                v = next(filter(lambda x: 'Value' in x[0], item.items()))
                if k in self._items:
                    self._items[k].configValue = v[1]
                    self._items[k].changed = False
                    self._items[k]._fromFile = v[1]
                else:
                    self.unknownConfig[k] = v

        self.config = config
        self.configVersionRead = 2  # Future: detect version?


    # =======================================================================
    #
    # =======================================================================

    def _getitem(self, item: Union[int, str]) -> ConfigItem:
        """ Get a configuration item, specified either by config ID or by label
            (if it has one).

            Note that labels are not guaranteed to be unique, but config IDs
            are. Strings must exactly match label text. Using config IDs is
            therefore recommended.

            :param item: The config ID or label of a configuration item.
            :return: The indicated `ConfigItem`.
        """
        if item in self.items:
            return self.items[item]

        s = hex(item) if isinstance(item, int) else repr(item)
        raise KeyError(item, "Config item {} not in CONFIG.UI data"
                       .format(s))


    def _setitem(self, item: Union[int, str], value: Optional[Any]):
        """ Set a configuration item, specified either by config ID or by label
            (if it has one).

            Note that labels are not guaranteed to be unique, but config IDs
            are. Strings must exactly match label text. Using config IDs is
            therefore recommended.

            :param item: The config ID or label of a configuration item.
        """
        # Somewhat redundant w/ VirtualConfigInterface, but just to be safe
        if self.device and self.device.isVirtual:
            raise ConfigError('Cannot configure virtual devices')
        self._getitem(item).value = value


    # =======================================================================
    # Simple, standard config items, giving names to config IDs. A couple do
    # a small amount of modification for convenience (e.g., UTC Offset).
    # =======================================================================

    @property
    def name(self) -> Union[str, None]:
        """ User-entered name of the device. """
        return self._getitem(0x08ff7f).value

    @name.setter
    def name(self, n: Optional[str]):
        self._setitem(0x08ff7f, n)

    @property
    def notes(self) -> Union[str, None]:
        """ User-entered notes/description of the device. """
        return self._getitem(0x09ff7f).value

    @notes.setter
    def notes(self, n: Optional[str]):
        self._setitem(0x09ff7f, n)

    @property
    def tags(self) -> Union[str, None]:
        """ The device's recording tags (comma-separated string), stored in
            each recording. Primarily used for organization on enDAQ Cloud.
        """
        return self._getitem(0x17ff7f).value

    @tags.setter
    def tags(self, t):
        self._setitem(0x17ff7f, t)

    @property
    def pluginAction(self) -> Union[int, None]:
        """ The ID of the device's Plug-In Action (what happens when
            attached by USB).
        """
        return self._getitem(0x0aff7f).value

    @pluginAction.setter
    def pluginAction(self, action: int):
        self._setitem(0x0aff7f, action)

    @property
    def pluginActions(self) -> Dict[int, str]:
        """ The IDs and descriptions of all known Plug-In Action options.
            Read only.
        """
        return self._getitem(0x0aff7f).options

    @property
    def buttonMode(self) -> Union[int, None]:
        """ The ID of the device's 'button mode' (what happens when the
            device's primary button is pressed).
        """
        return self._getitem(0x10ff7f).value

    @buttonMode.setter
    def buttonMode(self, mode: int):
        self._setitem(0x10ff7f, mode)

    @property
    def buttonModes(self) -> Dict[int, str]:
        """ The IDs and descriptions of all known Button Mode options.
            Read only.
        """
        return self._getitem(0x10ff7f).options

    @property
    def utcOffset(self) -> Union[float, int, None]:
        """ The recorder's local offset from UTC, in minutes. """
        # Convert from seconds to hours
        return self._getitem(0x0bff7f).value / 3600

    @utcOffset.setter
    def utcOffset(self, offset: Optional[float]):
        # Convert from hours to seconds
        self._setitem(0x0bff7f, int(offset * 3600))

    @property
    def recordingDir(self) -> Union[str, None]:
        """ The name of the directory (on the device) where recordings are saved. """
        return self._getitem(0x14ff7f).value

    @recordingDir.setter
    def recordingDir(self, dirname: Optional[str]):
        self._setitem(0x14ff7f, dirname)

    @property
    def recordingPrefix(self) -> Union[str, None]:
        """ Prefix string for all recording filenames. """
        return self._getitem(0x15ff7f).value

    @recordingPrefix.setter
    def recordingPrefix(self, prefix: Optional[str]):
        self._setitem(0x15ff7f, prefix)

    @property
    def recordingTimeLimit(self) -> Union[int, None]:
        return self._getitem(0x0dff7f).value

    @recordingTimeLimit.setter
    def recordingTimeLimit(self, t: Optional[int]):
        self._setitem(0x0dff7f, t)

    @property
    def recordingSizeLimit(self) -> Union[int, None]:
        return self._getitem(0x11ff7f).value

    @recordingSizeLimit.setter
    def recordingSizeLimit(self, t: Optional[int]):
        self._setitem(0x11ff7f, t)


    # =======================================================================
    # More complex (but standard) configuration items
    # =======================================================================

    def _encodeChannel(self,
                       channel: Union[Channel, SubChannel]) -> int:
        """ Create the low 2 bytes of a channel-specific config ID (low byte
            is channel ID, high byte is subchannel ID or 0xFF if not a
            `SubChannel`).

            :param channel: The channel or subchannel to encode
            :return: The encoded channel ID
        """
        if isinstance(channel, SubChannel):
            return channel.id << 8 | channel.parent.id
        elif isinstance(channel, Channel):
            return channel.id | 0xff00
        else:
            raise TypeError("Expected a Channel or SubChannel object, "
                            "got {}".format(type(channel)))


    def enableChannel(self,
                      channel: Union[Channel, SubChannel],
                      enabled: bool = True):
        """ Enable or disable a `Channel` or `SubChannel`.

            Due to the way in which they operate, some sensor's `SubChannels`
            cannot be individually configured, and changes must be made to
            the parent `Channel`. The opposite is true for other sensors -
            primarily the analog ones - which can only be configured at the
            `SubChannel` level. Attempting to configure at the wrong 'level'
            will raise a ``ConfigError``.

            :param channel: The channel or subchannel to enable/disable.
            :param enabled: `True` to enable the channel/subchannel recording.
        """
        configId = self._getChannelConfigId(0x010000, channel)
        enItem = self._getitem(configId)

        # Some subchannels (analog) are enabled explicitly with their own
        # config ID. Others (mostly digital) use bits in a single config item.
        if enItem.element.name.endswith('BitField'):
            # Some Channels without individually-configurable SubChannels use
            # a one-item BitField.
            if len(enItem.options) == 1:
                if isinstance(channel, SubChannel):
                    raise ConfigError('ConfigUI {} not applicable to {}; '
                                      'use a Channel instead'
                                      .format(enItem, channel))
                enabled = int(enabled)

            else:
                if not isinstance(channel, SubChannel):
                    raise ConfigError('ConfigUI {} not applicable to {}; '
                                      'use a SubChannel instead'
                                      .format(enItem, channel))

                val = enItem.value
                if val is None:
                    val = 2 ** len(channel.parent.children) - 1
                bit = (1 << channel.id)
                if enabled:
                    # Set
                    enabled = val | bit
                elif val & bit:
                    # Clear if set
                    enabled = val ^ bit
                else:
                    # No change
                    enabled = val

        enItem.value = enabled


    def isEnabled(self,
                  channel: Union[Channel, SubChannel]) -> bool:
        """ Is the `Channel` or `SubChannel` enabled?

            Due to the way in which they operate, some sensor's `SubChannels`
            cannot be individually configured, and changes must be made to
            the parent `Channel`. The opposite is true for other sensors -
            primarily the analog ones - which can only be configured at the
            `SubChannel` level. Attempting to configure at the wrong 'level'
            will raise a ``ConfigError``.

            :param channel: The `Channel` or `SubChannel` to check.
            :return: `True` if configured to record.
        """
        configId = self._getChannelConfigId(0x010000, channel)
        enItem = self._getitem(configId)
        en = enItem.value
        if enItem.element.name.endswith('BitField') and isinstance(channel, SubChannel):
            en = True if en is None else (int(en) & (1 << channel.id))
        return bool(en)


    def _getChannelConfigId(self,
                            configType: int,
                            channel: Union[Channel, SubChannel]) -> int:
        """ Get the config ID of a specific type for a channel. If the config
            ID for the specific subchannel doesn't exist, the config ID for
            the channel is returned (although it might not exist, either).
            For things like BitField values, in which there is one config
            item for the channel, and the bits of the value represent the
            subchannels.

            :param configType: A 24b value, with the high byte representing
                the configuration item type. Bits 0-15 are 0.
            :param channel: The channel or subchannel to configure.
            :return: The channel/subchannel configuration ID.
        """
        configId = configType | self._encodeChannel(channel)
        if configId not in self.items:
            configId |= 0x00ff00
        return configId


    def _getChannel(self, configId: int) -> Union[Channel, SubChannel, None]:
        """ Get the Channel/SubChannel corresponding to a configuration ID.
        """
        ch = configId & 0xFF
        subCh = configId >> 8 & 0xFF

        channel = self.device.channels.get(ch, None)
        if not channel:
            logger.debug('No channel for ConfigID {:x}'.format(configId))
            return None

        if subCh == 0xFF:
            return channel

        if subCh > len(channel.children):
            logger.debug('No subchannel for ConfigID {:x}'.format(configId))
            return None

        return channel[subCh]


    def setTrigger(self,
                   channel: Union[Channel, SubChannel],
                   **kwargs):
        """ Set the trigger for a `Channel` or `Subchannel`.

            :param channel: The channel or subchannel to configure.
            :keyword low: The trigger's low threshold value (if applicable).
            :keyword high: The trigger's high threshold value (if applicable).
                Also used for sensors that have only an absolute threshold
                trigger (e.g., a shock trigger).
            :keyword enabled: `True` to enable the channel/subchannel trigger.
                Threshold arguments are Values of `high` and `low` are optional if `False`.
        """
        loId = self._getChannelConfigId(0x030000, channel)
        hiId = self._getChannelConfigId(0x040000, channel)
        enId = self._getChannelConfigId(0x050000, channel)

        # Some sensors have a main channel-level trigger enable as well as
        # individual subchannel triggers. These main enables have a different
        # 'prefix' byte (0x07).
        if enId not in self.items and enId & 0x00ff00:
            enId = self._getChannelConfigId(0x070000, channel)

        # Fail before setting if any ConfigID is unknown is bad.
        if 'low' in kwargs and loId not in self.items:
            raise ConfigError('Cannot configure low trigger for {!r}'
                              .format(channel))
        if 'high' in kwargs and hiId not in self.items:
            raise ConfigError('Cannot configure high trigger for {!r}'
                              .format(channel))
        if 'enabled' in kwargs and enId not in self.items:
            raise ConfigError('Cannot configure enable for {!r}'
                              .format(channel))

        if 'low' in kwargs:
            self._setitem(loId, kwargs['low'])
        if 'high' in kwargs:
            self._setitem(hiId, kwargs['high'])
        if 'enabled' in kwargs:
            enItem = self._getitem(enId)
            if enItem.element.name.endswith('BitField') and isinstance(channel, SubChannel):
                en = enItem.value or 0
                bit = 1 << channel.id
                en = en | bit if kwargs['enabled'] else en ^ bit
            else:
                en = int(kwargs['enabled'])

            self._setitem(enId, en)


    def getTrigger(self,
                   channel: Union[Channel, SubChannel]) -> dict:
        """ Get the trigger information for a `Channel` or `SubChannel`.

            :param channel: The `Channel` or `SubChannel` to get.
            :return: A `dict` of trigger parameters, usable as keyword
                arguments for `setTrigger()`.
        """
        loId = self._getChannelConfigId(0x030000, channel)
        hiId = self._getChannelConfigId(0x040000, channel)
        enId = self._getChannelConfigId(0x050000, channel)

        trig = {}
        if loId in self.items:
            trig['low'] = self._getitem(loId).value
        if hiId in self.items:
            trig['high'] = self._getitem(hiId).value

        enItem = self._getitem(enId)
        en = enItem.value
        if enItem.element.name.endswith('BitField') and isinstance(channel, SubChannel):
            # Enabled is usually the default; change per-case if/when not
            en = True if en is None else bool(en & (1 << channel.id))
        trig['enabled'] = en

        return trig


    def setSampleRate(self,
                      channel: Channel,
                      sampleRate: float):
        """ Set the sample rate of a `Channel`.

            :param channel: The `Channel` to set.
            :param sampleRate: The new sampling rate, in hertz.
        """
        configId = 0x020000 | self._encodeChannel(channel)
        self._getitem(configId).value = sampleRate


    def getSampleRate(self,
                      channel: Channel) -> float:
        """ Get the sample rate of a `Channel`.

            :param channel: The `Channel` to get.
            :return: The sampling rate, in hertz.
        """
        configId = self._encodeChannel(channel) | 0x020000
        item = self._getitem(configId)
        return item.value if item.value is not None else item.default


    def getTriggers(self) -> List[ConfigItem]:
        """ Get all settable triggers (threshold, high, and/or low).

            :return: A list of all trigger configuration items.
        """
        return [v for v in self.items.values()
                if v.configId & 0xff0000 in (0x030000, 0x040000)]


# ===========================================================================
#
# ===========================================================================

class VirtualConfigInterface(ConfigInterface):
    """
    Read-only configuration interface for 'virtual' recorders (i.e., ones
    instantiated from IDE file metadata).
    """

    @classmethod
    def hasInterface(cls, device: "Recorder") -> bool:
        """
        Determine if a device supports this `ConfigInterface` type.

        :param device: The Recorder to check.
        :return: `True` if the device supports the interface.
        """
        return device.isVirtual and super().hasInterface(device)


    @property
    def available(self) -> bool:
        """ Is the device currently ready for configuration?
        """
        # Never!
        return False


    def getConfigUI(self) -> Union[Document, MasterElement]:
        """ Load the virtual device's ``ConfigUI`` data.
        """
        # Use existing data, or data taken from source file
        self.configUi = self.configUi or getattr(self.device, '_configUi', None)
        if self.configUi:
            return self.configUi
        else:
            ebml = ui_defaults.getDefaultConfigUI(self.device)
            self.configUi = self._schema.loads(ebml)

        if not self.configUi:
            raise IOError(errno.ENOENT, "No default ConfigUI found for {}"
                          .format(self.device.partNumber))

        return self.configUi


    def getConfig(self) -> Union[Document, MasterElement]:
        """ Low-level method that retrieves the device's config EBML (e.g.,
            the contents of a real device's ``config.cfg`` file), if any.
        """
        # This will have been cached when Recorder.fromRecording() was called
        return self.device._config


    def applyConfig(self, **kwargs):
        """ Apply modified configuration data to the device. Not supported on
            virtual devices!
        """
        raise UnsupportedFeature("Virtual devices cannot be configured")


    def _setitem(self, item: Union[int, str], value):
        """ Set a configuration item, specified either by config ID or by
            label (if it has one). Not supported on virtual devices!

            Note that labels are not guaranteed to be unique, but config IDs
            are. Strings must exactly match label text. Using config IDs is
            therefore recommended.

            :param item: The config ID or label of a configuration item.
        """
        raise UnsupportedFeature("Virtual devices cannot be configured")


    def revert(self):
        """ Reset all configuration values to what was originally read from
            the configuration file. Not supported on virtual devices!
        """
        raise UnsupportedFeature("Virtual devices cannot be configured")


# ===========================================================================
#
# ===========================================================================

class FileConfigInterface(ConfigInterface):
    """
    Standard configuration interface: uses the device's ``CONFIG.UI`` file
    (if present), and reads/writes a local device's ``config.cfg`` file.

    This interface also handles converting to and from the legacy
    configuration file format (version 1).
    """

    @classmethod
    def hasInterface(cls, device: "Recorder") -> bool:
        """
        Determine if a device supports this `ConfigInterface` type.

        :param device: The Recorder to check.
        :return: `True` if the device supports the interface.
        """
        if device.isVirtual:
            return False

        # Very simple initial check: is there a CONFIG.UI file?
        # Unlikely to fail, but in a `try` just in case.
        try:
            if os.path.isfile(device.configUIFile):
                return True
        except IOError:
            pass

        return super().hasInterface(device)


    @property
    def supportedConfigVersions(self):
        """ A tuple of configuration file format versions supported by
            the interface.
        """
        if self._supportedConfigVersions is not None:
            return self._supportedConfigVersions

        mcu = self.device.getInfo('McuType', 'EFM32GG330')
        if not mcu.startswith("EFM32GG330"):
            return ConfigInterface.supportedConfigVersions.fget(self)

        vers = (1,)

        if self.device.firmwareVersion > 14:
            vers += ConfigInterface.supportedConfigVersions.fget(self)

        self._supportedConfigVersions = vers
        return vers


    def _makeConfig(self, unknown: bool = True, version: Optional[int] = None,
                    defaults: bool = False) -> Dict[str, Any]:
        """ Generate a dictionary of configuration data, suitable for EBML
            encoding.

            Note: this is currently used directly by another project (the
            config GUI's exporter). Be careful modifying until import/export
            has been moved to this package and the config GUI is updated.

            :param unknown: If `True`, include configuration items in the
                `ConfigInterface`'s `unknownConfig`; items read from the
                configuration file but have IDs that do not correspond to
                fields in the device's ``ConfigUI`` data.
            :param version: The version of configuration data to use.
            :return: A dictionary of configuration values, ready for encoding
                as EBML.
        """
        supportedVersions = self.supportedConfigVersions
        if version is not None and version not in supportedVersions:
            raise ConfigError("Device does not support config data version {}, only {}".
                              format(version, supportedVersions))

        version = version or supportedVersions[-1]

        if version != 1:
            return super()._makeConfig(unknown=unknown)

        logger.debug('Writing legacy config file for {!r}'.format(self.device))
        vals = self.getConfigValues(defaults=defaults, original=False, unknown=unknown)
        return legacy.generateLegacyConfig(vals, self.device)


    def getConfigUI(self) -> Union[Document, MasterElement]:
        """ Load the device's ``ConfigUI`` data.
        """
        if not self.configUi:
            if os.path.isfile(self.device.configUIFile):
                with open(self.device.configUIFile, 'rb') as f:
                    self.configUi = self._schema.loads(f.read())
            else:
                ebml = ui_defaults.getDefaultConfigUI(self.device)
                if not ebml:
                    raise IOError(errno.ENOENT, "No default ConfigUI found for {}"
                                  .format(self.device))
                self.configUi = self._schema.loads(ebml)

        return self.configUi


    def getConfig(self) -> Union[Document, MasterElement]:
        """ Low-level method that retrieves the device's config EBML (e.g.,
            the contents of a real device's `config.cfg` file), if any.
        """
        try:
            if not os.path.isfile(self.device.configFile):
                return b''

            with open(self.device.configFile, 'rb') as f:
                return loadSchema('mide_ide.xml').loads(f.read())

        except IOError as err:
            warnings.warn("{}.getConfig(): ignoring possibly expected exception {!r}"
                          .format(type(self).__name__, err))
            return b''


    def loadConfig(self, config: Optional[MasterElement] = None):
        """ Process a device's configuration data.

            :param config: Optional, explicit configuration EBML data to
                process. If none is provided, the data retrieved by
                `getConfig()` will be used.
        """
        config = config or self.config or self.getConfig()
        if not config:
            self.config = {}
            return

        if config[0].name == "RecorderConfiguration":
            logger.debug("Reading legacy config file data from {}"
                         .format(self.device.configFile))
            versionRead = 1
            self._originalConfig = config  # for testing
            config = legacy.convertConfigFile(config, self)
        else:
            versionRead = 2

        super().loadConfig(config)
        self.configVersionRead = versionRead


    def applyConfig(self,
                    unknown: bool = True,
                    clear: bool = True,
                    version: Optional[int] = None):
        """ Save modified configuration data to the device.

            :param unknown: If `True`, include values read from the config
                file that did not correspond to known configuration items.
            :param clear: If `True`, mark all items as unchanged after
                application.
            :param version: The version of configuration data to use, if the
                device supports more than one. Defaults to the latest
                version supported.
        """
        if not self.available:
            raise IOError(errno.ENOENT, "Could not find {}; is it connected?"
                          .format(self.device))

        # Do encoding before opening the file, so it can fail safely and not
        # affect any existing config file.
        config = self._makeConfig(unknown, version=version)
        configEbml = loadSchema('mide_ide.xml').encodes(config, headers=False)

        try:
            util.makeBackup(self.device.configFile)
            with open(self.device.configFile, 'wb') as f:
                f.write(configEbml)

            if clear:
                for item in self.items.values():
                    item.changed = False

        except Exception:
            # Write failed, restore old config file
            util.restoreBackup(self.device.configFile, remove=False)
            raise


# ===========================================================================
#
# ===========================================================================

#: A list of all `ConfigInterface` types, used when finding a device's
#   interface. `VirtualConfigInterface` should go last. New interface types
#   defined elsewhere should append/insert themselves into this list (before
#   their superclass, if their `hasInterface()` is more specific).
INTERFACES = [FileConfigInterface, VirtualConfigInterface]
