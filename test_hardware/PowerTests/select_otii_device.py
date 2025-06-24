"""
select_otii_device.py
For connecting to and configuring the endaq power measurement setup.

Workflow:
    - open otii server
    - connect to otii server using credentials
    - reserve license, error if not available
    - configure otii for endaq tests environment
    - connect uart bridge from custom board
    - connect usb & power to desired endaq
    - connect to endaq using endaq.device
    - close serial communication for next script
"""


from otii_tcp_client import otii_client
from otii_tcp_client import arc
from otii_tcp_client import otii_connection
import time, os, json
from pathlib import Path
import endaq.device as ed
import Instruments.Bridge

# TODO: include tests for linux packages? usbmount is required.
# TODO: may want to include arguments for serial port and path to otii server

# Configure as necessary when using on windows.
WIN_PATH_OTII_SERVER = r'C:/Users/nconstanti/AppData/Local/otii3/app-3.5.2/resources/otii_server.exe'
WIN_PORT = r'COM17'


# runs immediately after argparse
def otii_main(endaq_type: str, timeout: int, verbose: bool):
    # OPEN OTII SERVER
    os.system('otii_server &')  # run server for linux. the "&" means run in a new process.
    print('Verbose: Otii server started. Attempting to connect...')

    # CONNECT OTII SERVER WITH CREDENTIALS
    client = otii_client.OtiiClient()
    otii = client.connect(licensing='manual')
    try:
        otii.return_license(4748)
    except Exception as e:
        print(f'Ran into error, hopefully license is available. Error = {e}')
    credential_path = str(Path(__file__).resolve().parent / 'credentials.json')
    print(f"Using credentials {credential_path=}")
    otii._login(credential_path)
    assert otii.get_licenses()[0]['available'], 'License not available'
    otii.reserve_license(4748)
    devices = otii.get_devices()
    time.sleep(10)
    assert len(devices) == 1, f'Expected to find exactly 1 Otii device connected, found {len(devices)} devices'
    device: arc.Arc = devices[0]
    otii.get_active_project()
    if endaq_type == 'Off':
        if verbose:
            print("Devices are off, exiting")
        # Note: auto_reserved_licenses will only be filled if your computer did not have a license already. To return your own license, go to https://www.qoitech.com/licenses
        return otii.auto_reserved_licenses

    # CONFIGURE FOR ENDAQ TESTS ENVIRONMENT
    device.set_main_voltage(3.7)
    device.set_max_current(1.0)
    device.set_exp_voltage(5)  # 5V to custom board
    device.enable_5v(True)
    device.enable_channel('mc', enable=True)  # mc = Main Current
    device.set_main(True)  # enable main power

    # CONNECT UART BRIDGE FROM CUSTOM BOARD
    port = WIN_PORT if os.name == 'nt' else '/dev/ttyUSB0'
    Uart = Instruments.Bridge.Bridge(port)  # Serial abstraction for communicating with Uart Bridge chip on custom board. __init__ handles connection.

    # CONNECT USB & POWER TO DESIRED ENDAQ
    print(f"Connecting device USB")
    if endaq_type == 's':
        Uart.gpio_pin_set(4, False)  # USB Power
        Uart.gpio_pin_set(5, False)  # USB Data
    elif endaq_type == 'w':
        Uart.gpio_pin_set(4, True)  # USB Power
        Uart.gpio_pin_set(5, True)  # USB Data
    else:
        raise Exception(f"Unhandled endaq type: {endaq_type}")

    # CONNECT ENDAQ - Fails after timeout
    timeout += time.time()
    get_devs: list = ed.getDevices()
    update_rate = 2
    next_update = time.time() + update_rate
    while not (len(get_devs) > 0 and get_devs[0].available):  # wait for connect
        time.sleep(0.25)
        try:
            get_devs = ed.getDevices()
        except ed.exceptions.DeviceTimeout as e:
            print(f"Got device timeout, waiting and retrying {e=}")

        if time.time() > timeout:
            raise Exception('Timeout on endaq connect')
        if time.time() > next_update and verbose:
            print("Trying to connect to device...")
            next_update = time.time() + update_rate
    # closes serial connection for next use.
    Uart.ser.close()
    print(f"Found {get_devs=}")


if __name__ == '__main__':
    import argparse
    argparser = argparse.ArgumentParser(description="""
        Otii Device Selector
        """)
    argparser.add_argument('EndaqType', choices=['w', 's', 'off'],
                           help="Input w/s/off; Connects to specified endaq. If Off is used, only connect Otii and "
                                "return Otii automation license.")
    argparser.add_argument('-t', '--timeout',
                           default=20, type=int,
                           help="Fails if endaq is not found after <timeout> seconds.")
    argparser.add_argument('-v', '--verbose',
                           action='store_true',
                           help='Prints program status updates for debugging.')
    args = argparser.parse_args()

    # Assert arg endaq_type is correct format
    assert isinstance(args.EndaqType, str), 'Endaq type must be W, S, or Off'
    args.EndaqType = args.EndaqType.lower()
    assert args.EndaqType in ['w', 's', 'off'], 'Endaq type must be W, S, or Off'

    if args.verbose:
        print(f"{args=}")

    otii_main(endaq_type=args.EndaqType, timeout=args.timeout, verbose=args.verbose)
