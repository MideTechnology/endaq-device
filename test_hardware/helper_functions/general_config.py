from pydantic import BaseModel, ConfigDict, PositiveInt, PositiveFloat, model_validator, NonNegativeInt, NonNegativeFloat
import endaq.device as ed
from typing_extensions import Self

GENERAL_CONFIG_IDS = {  
                'Name': 0x8FF7F,
                'Notes': 0x9FF7F,
                'CustomRecordingTags': 0x17FF7F,
                'FileNameStyle': 0x16FF7F,
                'RecordingDirectory': 0x14FF7F,
                'RecordingFilePrefix': 0x15FF7F,
                'PlugInAction': 0xAFF7F,
                'ButtonMode': 0x10FF7F,
                'UTCOffset': 0xBFF7F,

                # WIFI
                'WifiEnable': 0x18FF7F,
                'WifiWhileAsleep': 0x28FF7F,
                'WifiWhileTriggering': 0x29FF7F,
                'WifiWhileRecording': 0x2AFF7F,
                'WifiBrokerIPAddress': 0x25FF7F,
                'WifimDNSInstanceName': 0x2BFF7F,
                'WifiStreamRecordingData': 0x26FF7F,
                'WifiUploadFile': 0x19FF7F,

                # Triggers
                'TriggerMode': 0x12FF7F,
                'StartAtTime': 0xFFF7F,
                'PreRecordingDelay': 0xCFF7F,
                'RecordingTimeLimit': 0xDFF7F,
                'RecordingFileSizeLimit': 0x11FF7F,
                'Retrigger': 0xEFF7F,
                'WaitforAllSensorConditions': 0x13FF7F,
                'CtrlPadPressureTrigger': 0x50027, 
                'CtrlPadPressureTriggerLow': 0x30027, 
                'CtrlPadPressureTriggerHigh': 0x40027, 
                'InternalPressureTrigger': 0x50024, 
                'InternalPressureTriggerLow': 0x30024, 
                'InternalPressureTriggerHigh': 0x40024, 
                'CtrlPadTemperatureTrigger': 0x50127,
                'CtrlPadTemperatureTriggerLow': 0x30127,
                'CtrlPadTemperatureTriggerHigh': 0x40127,
                'InternalTemperatureTrigger': 0x50124,
                'InternalTemperatureTriggerLow': 0x30124,
                'InternalTemperatureTriggerHigh': 0x40124,
                'MainAccelerationTriggerLow': 0x3FF08,
                'MainAccelerationTriggerHigh': 0x4FF08,
                'AdxlAccelerationThreshold': 0x4FF50,
                'AdxlAccelerationTriggerEnable': 0x5FF50,
            }


class GeneralConfig(BaseModel):
    model_config = ConfigDict(extra='allow')
    WifiEnable: NonNegativeInt = 0
    WifiUploadFile: NonNegativeInt = 0
    PlugInAction: NonNegativeInt = 0
    ButtonMode: NonNegativeInt = 0
    TriggerMode: NonNegativeInt = 0
    PreRecordingDelay: NonNegativeInt = 0
    RecordingTimeLimit: NonNegativeInt = 0
    RecordingFileSizeLimit: NonNegativeInt = 0
    Retrigger: NonNegativeInt = 0
    WaitforAllSensorConditions: NonNegativeInt = 0
    CtrlPadPressureTrigger: NonNegativeInt = 0
    CtrlPadPressureTriggerLow: NonNegativeInt = 0
    CtrlPadPressureTriggerHigh: NonNegativeInt = 119999
    InternalPressureTrigger: NonNegativeInt = 0
    InternalPressureTriggerLow: NonNegativeInt = 0
    InternalPressureTriggerHigh: NonNegativeInt = 119999
    CtrlPadTemperatureTrigger: NonNegativeInt = 0
    CtrlPadTemperatureTriggerLow: int = -40
    CtrlPadTemperatureTriggerHigh: int = 80
    InternalTemperatureTrigger: NonNegativeInt = 0
    InternalTemperatureTriggerLow: int = -40
    InternalTemperatureTriggerHigh: int = 80
    MainAccelerationTriggerLow: NonNegativeInt = 0
    MainAccelerationTriggerHigh: NonNegativeInt = 0
    AdxlAccelerationThreshold: NonNegativeInt = 0
    AdxlAccelerationTriggerEnable: NonNegativeInt = 0

    @model_validator(mode='after')
    def max_min_checker(self) -> Self:
        if self.CtrlPadPressureTriggerLow > self.CtrlPadPressureTriggerHigh:
            print(f"Warning! CtrlPad Press Trigger low/high values are swapped. Unswapping them")
            self.CtrlPadPressureTriggerLow, self.CtrlPadPressureTriggerHigh = self.CtrlPadPressureTriggerHigh, self.CtrlPadPressureTriggerLow
        if self.CtrlPadTemperatureTriggerLow > self.CtrlPadTemperatureTriggerHigh:
            print(f"Warning! CtrlPad Temperature Trigger low/high values are swapped. Unswapping them")
            self.CtrlPadTemperatureTriggerLow, self.CtrlPadTemperatureTriggerHigh = self.CtrlPadTemperatureTriggerHigh, self.CtrlPadTemperatureTriggerLow
        if self.InternalPressureTriggerLow > self.InternalPressureTriggerHigh:
            print(f"Warning! Internal Press Trigger low/high values are swapped. Unswapping them")
            self.InternalPressureTriggerLow, self.InternalPressureTriggerHigh = self.InternalPressureTriggerHigh, self.InternalPressureTriggerLow
        if self.InternalTemperatureTriggerLow > self.InternalTemperatureTriggerHigh:
            print(f"Warning! Internal Temperature Trigger low/high values are swapped. Unswapping them")
            self.InternalTemperatureTriggerLow, self.InternalTemperatureTriggerHigh = self.InternalTemperatureTriggerHigh, self.InternalTemperatureTriggerLow
        if self.MainAccelerationTriggerLow > self.MainAccelerationTriggerHigh:
            print(f"Warning! Main Accel Trigger low/high values are swapped. Unswapping them")
            self.MainAccelerationTriggerLow, self.MainAccelerationTriggerHigh = self.MainAccelerationTriggerHigh, self.MainAccelerationTriggerLow
        return self

    def set_configs(self, dev: ed.Recorder, quick_config: bool=False, verbose: bool=False) -> bool:
        item_dict = self.model_dump()
        config_changed = False
        dev.config.revert()     # Remove any unsaved changes
        for key, value in item_dict.items():
            if key in GENERAL_CONFIG_IDS:
                cfg_id = GENERAL_CONFIG_IDS[key] 
                if cfg_id not in dev.config.items:
                    if verbose: print(f'setting {cfg_id} ({key}) does not exist')
                    continue    # Setting does not exist for the device
                if quick_config:
                    if dev.config.items[GENERAL_CONFIG_IDS[key]].value == value:
                        if verbose:
                            print(f"{key} is already at the target value ({value})")
                        continue
                try:
                    config_changed = True
                    dev.config.items[GENERAL_CONFIG_IDS[key]].value = value
                    if verbose:
                        print(f"Updating config {key} from {dev.config.items[GENERAL_CONFIG_IDS[key]].value=} to {value=}") 
                except KeyError:
                    print(f"Could not set {key} ({GENERAL_CONFIG_IDS[key]}) to {value}. Probably fine")
                except ValueError as ve:
                    print(f"WARNING! Value Error Could not set {key} ({GENERAL_CONFIG_IDS[key]}) to {value}. Error:\n{ve}")
            else:
                print(f"Unrecognized configuration element: {key=}, {value=}")
        return config_changed

