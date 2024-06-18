import sys

import endaq.device

# get device
dev = endaq.device.getDevices()[0]

# keep track of number of recordings created
t = 0

# specify timeout
timeout = 20

while True:
    try:
        # get status of recording
        dev.command.ping()

        # if sensor is idle
        if dev.command.status[0] == endaq.device.DeviceStatusCode.IDLE:
            t += 1
            # start recording
            print(f"---Starting recording {t}---")
            dev.command.startRecording(timeout=timeout)

        continue
    except KeyboardInterrupt:
        # stop test if interrupted
        sys.exit(1)
    except endaq.device.DeviceTimeout as e:
        print(f"Device Timeout: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Exception: {e}")