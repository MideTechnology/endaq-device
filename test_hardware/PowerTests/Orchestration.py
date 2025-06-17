"""
main.py:
High-level abstraction for taking power measurements.
IMPORTANT: configure WIN_PATH_ROOT as necessary! (see below imports)

Class Orchestrator:
    Exposes three low-level abstractions of physical devices (scripts Config, Otii, Uart) and uses them for higher-level functions.
    An instance of Orchestrator is used primarily by the configure_and_measure function.
    Properties:
        Config: Exposed static class from Config.py
        Uart: Exposed instance of class Uart.Bridge from Bridge.py
        Otii: Exposed instance of class Otii.Arc from Otii.py
    Methods:
        usb_connect(endaq_type): Connects S or W series to USB
        toggle_recording(): Simulates a button press on S and W enDAQs simultaneously
        disconnect(): disconnects Otii and Uart to avoid errors in future tests. Not strictly required
        safe_endaq_connect(): Returns a reference to Endaq. Waits for endaq connection until timeout. On timeout, attempt button press and try again up to 2 times.


def configure_and_measure(Orc, my_config_dict: dict, endaq_type, RECORD_TIME: float = 20.0, trigger_mode = False, debug_mode:bool=False) -> dict:
    Applies configuration to endaq and takes a power measurement. Uses Orchestrator extensively.

def safe_configure_and_measure(Orc, my_config_dict, endaq_type, RECORD_TIME: float = 20.0, _i=3) -> dict:
    Safe way to call configure_and_measure with error handling.

def bulk_measurement(config_file_path:str, endaq_type:str, debug_mode:bool=False, trigger_mode = None):
    Ingests a bulk configuration file, loops through sub-configs and uses configure_and_measure() to determine power draw. Generates a report under /reports/.


Custom Exceptions:
    NoConnection: Raised by Orchestrator.safe_endaq_connect() when device does not connect after timeout.
    UnrealisticData: Raised by configure_and_measure when avg current is within 0.0004 amps of the sleep current.
"""

import endaq.device as ed
import os, time, json
import PowerTests.Instruments.Endaq as Endaq
import PowerTests.Instruments.Otii as Otii
import PowerTests.Instruments.Bridge as Bridge
from dataclasses import dataclass


class Orchestrator:
    """ High level tools for enDAQ power tests.
    Exposes instances of _uart.Bridge, endaq_autoconfig, and Otii automation in one place. """
    def __init__(self, port='', verbose: bool = False):
        # Change PORT if necessary

        self.Endaq = Endaq.AutoConfig  # static class
        self.Otii = Otii.Arc() # connects to otii, turns on power
        self.Uart = Bridge.Bridge(port, verbose) # connects to serial

    def usb_connect(self, endaq_type:str):
        """Connects USB to desired endaq using Uart commands"""
        endaq_type = endaq_type.lower()
        if endaq_type == 's':
            self.Uart.gpio_pin_set(4, False) # USB Power
            self.Uart.gpio_pin_set(5, False) # USB Data
        elif endaq_type == 'w':
            self.Uart.gpio_pin_set(4, True)  # USB Power
            self.Uart.gpio_pin_set(5, True)  # USB Data
        else: raise ValueError(f'usb_connect: endaq_type parameter must be either S or W. Received {endaq_type}.')
        return self.Uart.gpio_state

    def power_connect(self, endaq_type:str):
        """Connects main power to desired endaq using Uart commands"""
        endaq_type = endaq_type.lower()
        if endaq_type == 's':
            self.Uart.gpio_pin_set(3, False)
        elif endaq_type == 'w':
            self.Uart.gpio_pin_set(3, True)
        else:
            raise ValueError(f'usb_connect: endaq_type parameter must be either S or W. Received {endaq_type}.')
        return self.Uart.gpio_state

    def toggle_recording(self):
        """Simulates a button press on S and W enDAQs simultaneously using Uart commands"""
        self.Uart.gpio_pin_set(7, True)
        time.sleep(0.5)
        self.Uart.gpio_pin_set(7, False)

    def disconnect(self):
        ''' Unmounts endaq, disconnects Otii, and closes Uart. Recommended before restarting orchestrator'''
        self.Endaq.unmount()
        self.Otii.disconnect()
        self.Uart.ser.close()

    def safe_endaq_connect(self, _i:int = 0, timeout:float = 60) -> ed.Recorder:
        '''
        Returns a reference to Endaq. Waits for endaq connection until timeout. On timeout, attempt button press and try again up to 2 times.
        :param _i: Tracks recursion depth. Max is 2 iterations.
        :return: (ed.Recorder) device reference.
        '''
        if os.name == 'posix': self.Endaq.enable_automount(True)
        t = time.time()
        get_devs: list = ed.getDevices()

        while not (len(get_devs) > 0 and get_devs[0].available):  # wait for connect
            time.sleep(0.25)
            get_devs = ed.getDevices()

            # check for timeout after 60 seconds, press button and call recursion
            if time.time() - t > timeout:
                if _i >= 2: raise NoConnection('Timeout on endaq connect')
                print('Timeout on endaq connect: attempting button press and returning')
                self.toggle_recording() # Button Press
                time.sleep(6)
                return self.safe_endaq_connect(_i+1)

        if os.name == 'posix': self.Endaq.enable_automount(False)
        return get_devs[0]


@dataclass()
class TimeSettings:
    SLEEP_STARTUP:float = 5.7 # 4.3 # time between USB connect and recording button press. Must be greater than the device startup time, which can be experimentally discovered.
    SLEEP:float = 0.2 # time over which average sleep current will be measured.
    RECORD_STARTUP:float = 3 # time the device takes to start recording after button press. If too low, this startup sequence will be averaged into the power measurement.
    RECORD:float = 60.0 # time over which average recording current will be measured.



def configure_and_measure(Orc:Orchestrator, my_config_dict:dict | None, endaq_type:str, trigger_mode:bool = False, debug_mode:bool=False) -> dict: # string return is for error handling
    '''
    Applies configuration to endaq and takes a power measurement. Uses Orchestrator extensively. Designed to be looped multiple times.

    :param Orc: (Orchestrator) Orchestrator reference (must be already initialized)
    :param my_config_dict: (dict) Represents a single endaq configuration. If None, no config will be applied. Information on dict format can be found in Endaq.py
    :param endaq_type: (str) 's' or 'w'
    :param RECORD_TIME: (float) the time that will be used to calculate average.
    :param trigger_mode: (bool) enables different logic for testing device power consumption in trigger mode.
    :param debug_mode: (bool) verbosity
    :return: (dict) Power measurement report. For details, see end of function
    '''
    # INIT
    start_time = time.time()
    endaq_type = endaq_type.lower()
    assert endaq_type in ['s', 'w'], 'invalid endaq type at configure_and_measure'

    # CONNECT TO ENDAQ
    if debug_mode: print(f'connecting to endaq {endaq_type}-series...')
    Orc.usb_connect(endaq_type)  # ensure connected to usb
    dev: ed.Recorder = Orc.safe_endaq_connect()

    # APPLY CONFIG
    if debug_mode: print(f'Endaq connected: {dev} Applying configuration...')
    if my_config_dict:
        Orc.Endaq.apply_config(dev, my_config_dict)
    del dev

    # UNMOUNT ENDAQ
    Orc.Endaq.unmount()

    # TAKE RECORDING
    if debug_mode: print('taking measurement...')
    Orc.usb_connect('w' if endaq_type == 's' else 's')  # disconnect USB
    Orc.Otii.start_recording()  # start otii recording
    time.sleep(TimeSettings.SLEEP_STARTUP + TimeSettings.SLEEP + 0.2)
    Orc.toggle_recording()  # waits 0.5
    time.sleep(TimeSettings.RECORD_STARTUP + TimeSettings.RECORD + 0.1)
    Orc.Otii.stop_recording()
    if debug_mode: print('connecting usb')
    Orc.Endaq.enable_automount(True)
    Orc.usb_connect(endaq_type)  # reconnect usb data
    Orc.toggle_recording()
    if trigger_mode: # Extra button press to exit trigger mode
        time.sleep(0.25)
        Orc.toggle_recording()

    # GET DATA FROM RECORDING
    if debug_mode: print('extracting data...')
    start_stop_times_slp = (TimeSettings.SLEEP_STARTUP, TimeSettings.SLEEP_STARTUP + TimeSettings.SLEEP)
    start_stop_times_avg = (TimeSettings.SLEEP_STARTUP + TimeSettings.SLEEP + TimeSettings.RECORD_STARTUP + 0.2, TimeSettings.SLEEP_STARTUP + TimeSettings.SLEEP + TimeSettings.RECORD_STARTUP + TimeSettings.RECORD + 0.2)
    avg = Orc.Otii.get_last_recording_stats(start_stop_times_avg[0], start_stop_times_avg[1])['average']
    slp = Orc.Otii.get_last_recording_stats(start_stop_times_slp[0], start_stop_times_slp[1])['average']
    if avg - slp < 0.0004: raise UnrealisticData(f'avg ({avg}) - slp ({slp}) < 0.0004')
    # Orc.Otii.export_last_recording(dir_output_recordings + '/' + str(i) + '-' + name + '.csv', verbose=False)  # output recording as csv to the directory

    # DEL OTII RECORDING
    Orc.Otii.del_all_recordings()

    # GET TEMPERATURE, CLEAR REC FILES
    if debug_mode: print('Reconnecting and extracting temperature...')
    dev = Orc.safe_endaq_connect()
    temp = Orc.Endaq.get_temperature(dev)
    Orc.Endaq.clear_recording_files()

    # FORMAT OUTPUT
    output_report = {'avg': avg, 'slp': slp, 'temp': temp, 'time_taken': time.time()-start_time, 'data_timestamps': {'avg': start_stop_times_avg, 'slp': start_stop_times_slp}}
    return output_report


def safe_configure_and_measure(Orc, my_config_dict:dict | None, endaq_type:str, trigger_mode = False, debug_mode:bool=False, _i=3) -> dict:
    '''
    Error Handling for configure_and_measure.
    :param Orc, my_config_dict, endaq_type, RECORD_TIME: see configure_and_measure
    :param _i: Max recursion depth (number of times to try measurement
    :return: None
    '''
    try:
        return configure_and_measure(Orc, my_config_dict, endaq_type, trigger_mode = trigger_mode, debug_mode = (_i == 1 or debug_mode)) # Enables debug mode during final recursion, or parameter override
    except NoConnection as err:
        print('Endaq failed to connect. Escalating error...')
        raise err
    except Exception as err:
        if str(err) == 'Transaction id mismatch':
            print('Caught Transaction Id Mismatch. Escalating error...')
            raise Exception('Transaction Id Mismatch >:(')
        if _i <= 1:
            print('Measurement failed three times in a row. Escalating error...')
            raise UnknownError(f'Unknown Error: {err}')

        # Recursion
        print(f'Received {err}, trying again...')
        return safe_configure_and_measure(Orc, my_config_dict, endaq_type, _i - 1)


def bulk_measurement(config_file_path:str, endaq_type:str, trigger_mode:bool = False, debug_mode:bool=False) -> str:
    '''
    Ingests a bulk configuration file, loops through sub-configs and uses configure_and_measure() to determine power draw. Generates a report under /reports, returns a path to report.
    :param config_file_path: Path to file AFTER /configs/
    :param endaq_type: 's' or 'w'
    :param debug_mode: (bool) Verbosity
    :return: (str) filepath to report.json
    '''
    endaq_type = endaq_type.lower()

    # Initialize Orchestrator (connect to peripherals)
    print('connecting to otii, uart...') # prints regardless of debug mode
    Orc = Orchestrator(debug_mode)
    Orc.power_connect(endaq_type)
    Orc.usb_connect(endaq_type)

    # get start time
    st = time.time() # as seconds
    st_str = time.ctime() # as human-readable string

    # load configuration file from JSON into dictionary my_config_dict
    with open('configs/' + config_file_path, 'r') as f:
        my_config_dict = json.load(f)
    n_configs = len([k for k in my_config_dict.keys() if not '#CMD' in k]) # counts number of configs in my_config_dict, excluding commands.
    expected_time = n_configs*(7.5+60.0+20)/60 + 0.1
    print(f'taking {n_configs} measurements; done in approx. {expected_time} minutes') # prints regardless of debug mode

    # Create empty output directories
    dir_output_parent = 'reports/' + ('-'.join(config_file_path.split('/'))[:-5]) # path to output report.
    dir_output_recordings = dir_output_parent + '/raw_recordings'
    if not os.path.isdir(dir_output_parent):
        os.mkdir(dir_output_parent)
        os.mkdir(dir_output_recordings)

    # Measurement Loop
    output_report = {}  # this dictionary will be written under dir_output_main as file 'report.json' under key 'report'
    i = 0
    for name, c in my_config_dict.items():
        # COMMAND HANDLING (skips measurement, applies command)
        if '#CMD' in name:
            if 'Apply External' in name: # open external config json and apply the first config
                c:str # in this case, c is path to external config.
                with open('configs/' + c, 'r') as f:
                    external_config = list(json.load(f).values())[0]
                dev = Orc.safe_endaq_connect() # connect endaq
                Orc.Endaq.apply_config(dev, external_config) # apply config
            continue

        i += 1 # if it's not a command, increment.
        c:dict # if it's not a command, c must be a configuration dictionary.

        # TAKE POWER MEASUREMENT
        power_data = safe_configure_and_measure(Orc, c, endaq_type, trigger_mode=trigger_mode, debug_mode=debug_mode)

        # OUTPUTS
        # Orc._otii.export_last_recording(dir_output_recordings + '/'+str(i)+'-'+name+'.csv', verbose=False) # dump csv to the directory
        output_report[name] = power_data
        print(f'{i}/{n_configs} | {name}: {power_data}')


    # GENERATE REPORT
    time_taken = (time.time() - st)
    report = {
        'report': output_report,
        'time':{'start':st_str, 'end':time.ctime(), 'startup_time': TimeSettings.SLEEP, 'record_time':TimeSettings.RECORD, 'average_seconds_per_measurement': time_taken/n_configs, 'actual_minutes':time_taken/60, 'expected_minutes':expected_time},
        'config': my_config_dict
    }
    with open(dir_output_parent + '/report.json', 'w') as f:
        f.write(json.dumps(report))

    Orc.disconnect()

    return dir_output_parent + '/report.json'


''' Custom Exceptions '''
class NoConnection(Exception):
    def __init__(self, message):
        super().__init__(message)
class UnrealisticData(Exception):
    def __init__(self, message):
        super().__init__(message)
class UnknownError(Exception):
    def __init__(self, message):
        super().__init__(message)

if __name__ == '__main__':
    import argparse

    argparser = argparse.ArgumentParser(description="""
        Automated power tester!
        """)
    argparser.add_argument('-c', '--config',
                           default="w8_tests//main_accel.json",
                           help="Input config file.")

    argparser.add_argument('-p', '--power',
                           action="STORE_TRUE",
                           help="Input config file.")

    args = argparser.parse_args()

    bulk_measurement(args.config, debug_mode=False, endaq_type='w', trigger_mode=False)
