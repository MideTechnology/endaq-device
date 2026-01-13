import endaq.device
import time
import sys

def safe_get_device(device_sn: str = '', timeout: int = 30, unmounted=False) -> endaq.device.Recorder:
    out_of_time = False
    start_time = time.time()
    while not out_of_time:
        if time.time() - start_time > timeout:
            out_of_time = True
        devices = endaq.device.getDevices(unmounted=unmounted)
        if len(devices) == 0:
            continue
        for dev in devices:
            if not device_sn or dev.serial.lower() == device_sn.lower():
                print(f'Connected after {time.time() - start_time}')
                return dev
        if not out_of_time:
            time.sleep(1)
    devices = endaq.device.getDevices()
    raise endaq.device.exceptions.DeviceError(
        f'Could not find device {device_sn} in {timeout} seconds. Attached Devices: {devices}')

print(f'{sys.version=}')
dev = safe_get_device()
dev.config.item[1638271].value = 0
dev.command.reset()
dev = safe_get_device()
dev.config.item[1638271].value = 1
dev.command.reset()
dev = safe_get_device()
print(f'{dev.config.item[1638271]=}')
dev.command.getNetworkAddress()