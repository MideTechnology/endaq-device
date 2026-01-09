from pydantic import BaseModel, ConfigDict, PositiveInt, PositiveFloat, model_validator, NonNegativeInt, NonNegativeFloat
import endaq.device as ed
from typing_extensions import Self

GENERAL_CONFIG_IDS = {  
                'DeviceName': 589695,
                'DeviceNotes': 655231,
                'CustomRecordingTags': 1572735,
                'FileNameStyle': 1507199,
                'RecordingDirectory': 1376127,
                'RecordingFilePrefix': 1441663,
                'PlugInAction': 720767,
                'ButtonMode': 1113983,
                'UTCOffset': 786303,

                # WIFI
                'WifiEnable': 1638271,
                'WifiWhileAsleep': 2686847,
                'WifiWhileTriggering': 2752383,
                'WifiWhileRecording': 2817919,
                'WifiBrokerIPAddress': 2490239,
                'WifimDNSInstanceName': 2883455,
                'WifiStreamRecordingData': 2555775,

                # Triggers
                'TriggerMode': 1245055,
                'StartAtTime': 1048447,
                'PreRecordingDelay': 851839,
                'RecordingTimeLimit': 917375,
                'RecordingFileSizeLimit': 1179519,
                'Retrigger': 982911,
                'WaitforAllSensorConditions': 1310591,
                'CtrlPadPressureTrigger': 327719,
                'CtrlPadPressureTriggerLow': 196647,
                'CtrlPadPressureTriggerHigh': 262183,
                'InternalPressureTrigger': 327716,
                'InternalPressureTriggerLow': 196644,
                'InternalPressureTriggerHigh': 262180,
                'CtrlPadTemperatureTrigger': 327975,
                'CtrlPadTemperatureTriggerLow': 196903,
                'CtrlPadTemperatureTriggerHigh': 262439,
                'InternalTemperatureTrigger': 327972,
                'InternalTemperatureTriggerLow': 196900,
                'InternalTemperatureTriggerHigh': 262436,
                'MainAccelerationTriggerLow': 261896,
                'MainAccelerationTriggerHigh': 327432,
                '40gAccelerationThreshold': 327504,
                '40gAccelerationTriggerEnable': 393040,
            }


class GeneralConfig(BaseModel):
    model_config = ConfigDict(extra='allow')
    WifiEnable: NonNegativeInt = 0
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

    def set_configs(self, dev: ed.Recorder, quick_config: bool=False) -> bool:
        item_dict = self.model_dump()
        config_changed = False
        for key, value in item_dict.items():
            if key in GENERAL_CONFIG_IDS:
                if GENERAL_CONFIG_IDS[key] not in dev.config.items:
                    continue    # Setting does not exist for the device
                if quick_config:
                    if dev.config.items[GENERAL_CONFIG_IDS[key]].value == value:
                        print(f"{key} is already at the target value ({value})")
                        continue
                try:
                    config_changed = True
                    dev.config.items[GENERAL_CONFIG_IDS[key]].value = value
                except KeyError:
                    print(f"Could not set {key} ({GENERAL_CONFIG_IDS[key]}) to {value}. Probably fine")
                except ValueError as ve:
                    print(f"WARNING! Value Error Could not set {key} ({GENERAL_CONFIG_IDS[key]}) to {value}. Error:\n{ve}")
            else:
                print(f"Unrecognized configuration element: {key=}, {value=}")
        return config_changed

