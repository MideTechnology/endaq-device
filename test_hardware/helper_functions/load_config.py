from typing import Optional
import endaq.device as ed
import sys
from pathlib import Path
import shutil
from test_hardware.helper_functions.general_config import GeneralConfig
import test_hardware.helper_functions.actions_utils as au


if __name__ == "__main__":
    # TODO: Make this more general, maybe use env setting
    devs = ed.getDevices(unmounted=False)
    if len(devs) != 1:
        au.error(f"Found {len(devs)} devices attached ({devs}), expected 1. Using the 1st device, this will probably fail", title="Load Config")

    dev = devs[0]
    print("device: " + str(dev))
    if len(sys.argv[1:]) > 0:
        print(f"Loading config file {sys.argv[1]}")
        targets = Target(sys.argv[1])
        test_params = get_test_params(sys.argv[1])
    else:
        # TODO: Simplify loading in the base config
        des = dev.path + "/SYSTEM/config.cfg"
        configPath = Path.cwd() / "firmware_tests" / "configs"
        for file in configPath.iterdir():
            if dev.serial == file.name[:8]:
                print(f"Loading config file {file.absolute()}")
                shutil.copyfile(file, des)
                break
        targets = Target(None)
        test_params = get_test_params(source=None)
    set_sensor_config(dev, targets, duration=test_params.duration)
    general_config = GeneralConfig(**test_params.general_config)
    general_config.set_configs(dev)
    dev.config.applyConfig()
    with au.Group("Device Config"):
        for config_id, value in dev.config.items.items():
            print(f"{config_id}: {value.value}")

