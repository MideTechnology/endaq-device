from ebmlite.core import loadSchema
from typing import Union, Dict, Optional, TYPE_CHECKING
from copy import deepcopy
from pathlib import Path

from ebmlite.core import MasterElement

__ALL__ = ["ConfigHelper"]

class ConfigHelper:
    """
    Both config options include a built-in time limit of 120 seconds. 
    Wifi information contains the same as the base config, with the addition of
    enabled wifi when idle, triggering, and recording, no endaq-cloud settings, and 
    . the ip address is set to user preference
    
    """
    @staticmethod
    def to_master_element(p: Path):
        with open(p, 'rb') as cfg:
            return loadSchema('mide_ide.xml').loads(cfg.read())

    @staticmethod
    def get_config(
            prefix: Optional[str] = None, 
            path: Optional[Path] = None,
            ipaddr: str = ""
            ) -> Union[Dict, Path]:
        """

        :param prefix: populates fields with a prefix, typically used to differentiate between sessions.
            This prefix will populate: The device name, notes, and recording directory.
            If left blank, the defaults will be maintained.
        :param path: Note that this will overwrite any contents if it already exists.
        :param wifi: a string 

        :return: a Dict following `mide.xml` formatting in ebmlite, otherwise returing
            the path given in the :param:path variable
        """
        new_cfg = deepcopy([_base_no_wifi_config, _base_wifi_config][ipaddr == ""].dump())
        modification_values = []
        new_cfg_rci = new_cfg['RecorderConfigurationList']['RecorderConfigurationItem']
        ids_in_list = map(lambda x: x['ConfigID'], new_cfg_rci)
        if prefix is not None:
            modification_values += [
                (0x8ff7f, 'TextValue', prefix), 
                (0x9ff7f, "TextValue", "note: " + prefix), #notes
                (0x0dff7f,'UIntValue', 120), #Recording time limit
                (0x14ff7f, "ASCIIValue", prefix + "_RECORD") #recdir
                ]
        if ipaddr:
            modification_values.append((0x25ff7f, 'ASCIIValue', ipaddr))
        for id, v_type, change_to in modification_values:
            if id in ids_in_list:
                new_cfg_rci[ids_in_list.index(id)][v_type] = change_to
            else:
                new_cfg_rci.append({'ConfigID': id, v_type: change_to})

        if path is None:
            return new_cfg
            
        with open(path, 'wb') as f:
            loadSchema('mide_ide.xml').encode(f, new_cfg)
            
    @staticmethod
    def reset_device_config(
        device, 
        prefix: Optional[str] = None,
        ipaddr: str=None
        ) -> bool:
        """
        resets the device configuration to the "base"

        :return: a boolean, dictating if the operation was successful
        """
        try:
            device.config.revert()
            devsyspath = Path(device.path) / Path('SYSTEM/config.cfg') 
            ConfigHelper.get_config(prefix, devsyspath, ipaddr)
            device.config.loadConfig() 
            device.command.reset()
            device.command.awaitReconnect(timeout = 60)
            return True
        except:
            return False

    @staticmethod
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
        #NOTE: the implementation of ebml document equivalence is not what we want,
        #      instead, we convert it down to a dictionary, which has our wanted equality checks
        try:
            if isinstance(cfg_a, Path): cfg_a = ConfigHelper.to_master_element(cfg_a)
            if isinstance(cfg_b, Path): cfg_b = ConfigHelper.to_master_element(cfg_b)
            if isinstance(cfg_a, MasterElement): cfg_a = cfg_a.dump()
            if isinstance(cfg_b, MasterElement): cfg_b = cfg_b.dump()
        except:
            #most likely due to a path not existing / not being a "MasterElement" path.
            return None

        return cfg_a == cfg_b
    
_base_no_wifi_config = ConfigHelper.to_master_element(
    Path("./test_hardware/helper_functions/no_wifi.cfg")
    ) #TODO: update both to contain a rec time limit of 120
_base_wifi_config: MasterElement = ConfigHelper.to_master_element(
    Path("./test_hardware/helper_functions/wifi.cfg")
    )
