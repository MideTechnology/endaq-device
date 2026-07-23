from ebmlite.core import loadSchema
from typing import Union, Literal, Dict, Optional, Tuple, Any, List, TYPE_CHECKING
from copy import copy, deepcopy
from pathlib import Path
from io import BytesIO
from ebmlite.core import MasterElement

__ALL__ = ["revert_to_base", "equal_cfg", "from_master_element", "to_master_element", "create_serial_config", "create_wifi_config"]


def revert_to_base(device, me: MasterElement) -> bool:
    """
    updates the device's config file to the default configuration.

    :param device: the device to update
    :param virtual: dictates if a serial (False) or virtual (True) connection is used.

    :return: if there was data to change.
    """
    if equal_cfg(device.config.getConfig, me):
        return False
    device.config.loadConfig(me)
    device.config.applyConfig()
    device.command.awaitReconnect(timeout=30)

def equal_cfg(
    cfg_a : Union[dict, MasterElement, Path], 
    cfg_b: Union[dict, MasterElement, Path]
    ) -> Optional[bool]:
    """
    Determines if two cfg instances are equal, defined in params.
    
    :param cfg_a: configuration information, either as a path, 
        or the dumped output from dev.config.config.dump()
    :param cfg_b: configuration information, either as a path, 
        or the dumped output from dev.config.config.dump()

    :return: None if the operation was unable to be performed, otherwise a boolean.
    """
    try:
        if isinstance(cfg_a, Path): cfg_a = to_master_element(cfg_a)
        if isinstance(cfg_b, Path): cfg_b = to_master_element(cfg_b)
        if isinstance(cfg_a, MasterElement): cfg_a = cfg_a.dump()
        if isinstance(cfg_b, MasterElement): cfg_b = cfg_b.dump()
    except:
        #most likely due to a path not existing / not being a "MasterElement" path.
        return None

    return cfg_a == cfg_b

def from_master_element(
        me: MasterElement, 
        to: Literal['BytesIO', 'dict']
        ) -> Union[BytesIO, Dict]:
    """
    Converts a `mide_ide.xml` formatted Master Element to the `to` type.
    
    :param me: MasterElement to convert.
    :param to: dictates what to convert to. 
    """
    d = me.dump()
    if to.lower() == "dict":
        return d
    return loadSchema("mide_ide.xml").encodes(d)

def to_master_element(data: Union[Path, dict[str, Any], BytesIO]) -> MasterElement:
    """
    Converts compatible data to a `mide_ide.xml` formatted Master Element. 

    :param data: data to convert

    :return: a MasterElement of the new data
    """
    schema = loadSchema('mide_ide.xml')
    if isinstance(data, Path):
        with open(data, 'rb') as cfg:
            return schema.loads(cfg.read())
    elif isinstance(data, dict):
       data = schema.encodes(data)
    return schema.loads(data)

def create_serial_config(uuid: str) -> MasterElement:
    """
    Creates a MasterElement with the minimum requriements for a device
    that is to be connected by a serial connection.

    :param uuid: a string to populate the config with. Note that this does
        not need to be a literal uuid, just an identifying string.

    :return: a master element with the fields `name`, `notes`, and `recording directory`
        populated, alongn with a 120 second recording time limit
    """
    mod_values = [
        (0x8ff7f, 'TextValue', uuid), 
        (0x9ff7f, "TextValue", "note: " + uuid), #notes
        (0x0dff7f,'UIntValue', 120), #Recording time limit
        (0x14ff7f, "ASCIIValue", uuid + "_RECORD") #recdir
        ]
    return _apply_mod_values({}, mod_values, "MasterElement")

def create_wifi_config(uuid: str, ip_addr: str) -> MasterElement:
    """
    creates a MasterElement for a wifi-based enDAQ device with the minimum requirements
    to be connected via WiFi. 

    :param uuid: a string to populate the config with. Note that this does
        not need to be a literal uuid, just an identifying string.

    :return: a MasterElement with `name`, `notes`, `recording directory` populated, 
        flags for wifi, and an 120 second recording time limit

    """
    mod_values = [
        (0x8ff7f, 'TextValue', uuid), 
        (0x9ff7f, "TextValue", "note: " + uuid), #notes
        (0x0dff7f,'UIntValue', 120), #Recording time limit
        (0x14ff7f, "ASCIIValue", uuid + "_RECORD"), #recdir
        (0x25ff7f, 'ASCIIValue', ip_addr), #ip addr
        (0x18ff7f, 'UIntValue', 1), #Allow wireless
        (0x26ff7f, 'UIntValue', 1), #Wireless Control
        (0x28ff7f, 'UIntValue', 1), #Control while asleep
        (0x29ff7f, 'UIntValue', 1), #Control while Triggering
        (0x2aff7f, 'UIntValue', 1), #Control while Recording
        #FUTURE: having some issues retreving proper MQTTConnector with custom names.
        #        change enDAQ to uuid when solved
        (0x2bff7f, 'ASCIIValue', uuid),
        #(0x2bff7f, 'ASCIIValue',  "enDAQ"+ " Remote Interface"), #Advertising name
        (0x2cff7f, 'UIntValue', 1), #Stream Data
        ]
    return _apply_mod_values({}, mod_values, "MasterElement")

def _apply_mod_values(
        rci: Union[Dict, List[Dict[str, Any]]], 
        mod_values: List[Tuple], 
        output: Literal["dict", "MasterElement"]
        ) -> Union[Dict, MasterElement]:
    """
    Helper for the creation of MasterElements, applying values and converting if specified.

    :param rci: a list of dictionaries containing Recorder Configuration Items,
        achieved from MasterElement.dump()['RecorderConfigurationList']['RecorderConfigurationItem']
    :param mod_values: a List of modification value tuples, 
        which has the form (hex code, encoding type, value)
    :output: dictates output form

    :return: a Dictionary with the updated values or a MasterElement, dictated by `output`

    """
    if not isinstance(rci, dict):
        rci = deepcopy(rci)
        ids_in_list = filter(lambda x : x is not None, 
                             map(lambda x: x.get('ConfigID', None), rci)
                             )
    else:
        ids_in_list = []
        rci = []
    for hex_id, v_type, change_to in mod_values:
        if hex_id in ids_in_list:
            rci[ids_in_list.index(hex_id)][v_type] = change_to
        else:
            rci.append({
                'ConfigID': hex_id,
                v_type: change_to
                })
    if output.lower() == "dict":
        return rci
    return to_master_element(
            {'RecorderConfigurationList':
             {'RecorderConfigurationItem': rci}
             })
