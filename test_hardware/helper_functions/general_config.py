from ebmlite.core import loadSchema
from typing import Union, Literal, Dict, Optional, Tuple, Any, List, TYPE_CHECKING
from copy import copy, deepcopy
from pathlib import Path
from io import BytesIO
from ebmlite.core import MasterElement

__ALL__ = ["ConfigHelper"]


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
        if isinstance(cfg_a, Path): cfg_a = ConfigHelper.to_master_element(cfg_a)
        if isinstance(cfg_b, Path): cfg_b = ConfigHelper.to_master_element(cfg_b)
        if isinstance(cfg_a, MasterElement): cfg_a = cfg_a.dump()
        if isinstance(cfg_b, MasterElement): cfg_b = cfg_b.dump()
    except:
        #most likely due to a path not existing / not being a "MasterElement" path.
        return None

    return cfg_a == cfg_b

def from_master_element(me: MasterElement, to: Literal['BytesIO', 'dict']):
    """
    Converts a Master Element to the `to` type.
    
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
    """
    schema = loadSchema('mide_ide.xml')
    if isinstance(data, Path):
        with open(data, 'rb') as cfg:
            return schema.loads(cfg.read())
    elif isinstance(data, dict):
       data = schema.encodes(data)
    return schema.loads(data)

class ConfigLocker:
    """
    Both config options include a built-in time limit of 120 seconds. 
    Wifi information contains the same as the base config, with the addition of
    enabled wifi when idle, triggering, and recording, no endaq-cloud settings, and 
    . the ip address is set to user preference
    
    """
    
    serial_config: MasterElement
    virtual_config: Optional[MasterElement]

    def __init__(self, uuid: str = None, ip_addr: Optional[str] = None):
        """
        
        """
        new_cfg_rci = {}
        mod_values = [
            (0x8ff7f, 'TextValue', uuid), 
            (0x9ff7f, "TextValue", "note: " + uuid), #notes
            (0x0dff7f,'UIntValue', 120), #Recording time limit
            (0x14ff7f, "ASCIIValue", uuid + "_RECORD") #recdir
            ]
        self.serial_config = self._apply_mod_values(new_cfg_rci, mod_values, "MasterElement")

        if bool(ip_addr): 
            mod_values.append((0x25ff7f, 'ASCIIValue', ipaddr))#ip address
            mod_values.append((0x28ff7f, 'UIntValue', 1)) #Control while asleep
            mod_values.append((0x29ff7f, 'UIntValue', 1)) #Control while Trigger
            mod_values.append((0x2aff7f, 'UIntValue', 1)) #Control while Recording
            mod_values.append((0x2bff7f, 'ASCIIValue', "enDAQ Remote Interface")) #mDNS name
            self.virtual_config = self._apply_mod_values(new_cfg_rci, mod_values, "MasterElement")
        else:
            self.virtual_config = None

    def _apply_mod_values(
            self, 
            rci: Union[Dict, List[Dict[str, Any]]], 
            mod_values: List[Tuple], 
            output: Literal["dict", "MasterElement"]
            ) -> Union[Dict, MasterElement]:
        """

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

    def get_config(
            self,
            virtual: bool,
            form: Literal["dict", "MatserElement"] = "MasterElement"
            ) -> Optional[Union[dict, MasterElement]]:
        """
        Convinience getter for config info.

        :param virtual: dictates which config value to get
        :param form: dictates return type, where dict is the dumped master element

        :return: a dict or MasterElement, dependent on :param:`form`
        """
        
        me = [self.serial_config, self.virtual_config][int(virtual)]
        if form.lower() == "masterelement":
            return me
        return from_master_element(me, "dict")

    def revert_to_base(self, device, virtual) -> bool:
        """
        
        :return: if there was data to change.
        """
        base_config = self.get_config(virtual)
        if equal_cfg(device.config.getConfig, base_config):
            return False
        device.config.loadConfig(base_config)
        pass

