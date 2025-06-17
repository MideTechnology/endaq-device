from otii_tcp_client import otii_client
from otii_tcp_client import arc
import time, os

def open_file(filename):
    import os, sys, subprocess
    print(sys.platform)
    if sys.platform == "win32":
        os.startfile(filename)
    else:
        os.system('otii_server &') # run server for linux. the "&" means run in a new process.


"""
Class Arc
Automate connecting to Otii Arc, take measurements, get data, and export to csv. 
Currently configured for endaq power tests environment. Used primarily in Orchestration.py.

Methods:
    __init__(): 
        Start Otii TCP server, connect to Otii Arc, configure for endaq power tests environment.
    
    start_recording(): 
        Starts a new recording on connected Otii.
    
    stop_recording(): 
        Stops recording. Error if not taking a recording
    
    disconnect(): 
        Disables power and frees license

    get_last_recording_stats(FROM_TIME:float, TO_TIME:float) -> dict:
        Get min, max, average, and energy statistics from the last recording over a specified time frame.
        :param FROM_TIME: (float) start of frame
        :param TO_TIME: (float) end of frame
        :return: (dict) see example: {'min': 0.023, 'max': 0.032, 'avg': 0.025, 'energy': 0.026}

    export_last_recording(output_file_path:str, extra_recording_info:bool = False, verbose:bool = False):
        Exports the last recording to csv, with options to include extra recording info.
        :param output_file_path: the export filename. All files output under raw_recordings dir.
        :param extra_recording_info: include peripheral data in csv. Default False
        :param verbose: print estimated export time to console. Default False
        :return: None

"""

# must change on diff platform:
PATH_TO_OTII_SERVER = r'C:\Users\nconstanti\AppData\Local\otii3\app-3.5.2\resources\otii_server.exe'

class Arc:
    def __init__(self, main_voltage = 3.7, max_current = 1):
        # start otii client server
        open_file(PATH_TO_OTII_SERVER)

        # Connecting to server, device
        client = otii_client.OtiiClient()
        self.otii = client.connect()
        devices = self.otii.get_devices()
        assert len(devices) == 1, f'Expected to find exactly 1 Otii device connected, found {len(devices)} devices'
        self.device: arc.Arc = devices[0]
        self.project = self.otii.get_active_project()

        # Configure for endaq tests environment
        self.device.set_main_voltage(main_voltage)
        self.device.set_max_current(max_current)
        self.device.set_exp_voltage(5) # Digital Voltage
        self.device.enable_5v(True) # 5V to custom board
        self.device.enable_channel('mc', enable=True)  # mc = Main Current
        self.device.set_main(True) # enable main power

    def start_recording(self) -> None:
        """ Starts a new recording on connected Otii """
        self.project.start_recording()

    def stop_recording(self) -> None:
        """ Stops recording """
        self.project.stop_recording()

    def disconnect(self) -> None:
        """ Disables power and frees license """
        try:
            self.otii.disconnect()
        finally:
            print('Warning: otii disconnect failed')

    def get_last_recording_stats(self, FROM_TIME:float, TO_TIME:float) -> dict:
        """
        Get min, max, average, and energy statistics from the last recording over a specified time frame.
        :param FROM_TIME: (float) start of time frame
        :param TO_TIME: (float) end time
        :returns a dictionary like {'min': 0.023, 'max': 0.032, 'avg': 0.025, 'energy': 0.026}
        """
        recording = self.project.get_last_recording()
        stats:dict = recording.get_channel_statistics(self.device.id, 'mc', FROM_TIME, TO_TIME)
        return stats # stats dict has keys min, max, average, energy

    def export_recording(self, recording, output_file_path:str = 'my_output.csv', verbose:bool=False) -> None:
        """
        Exports the last recording to csv, with options to include extra recording info.
        :param recording: recording object to export
        :param output_file_path: (str) the export filepath.
        :param verbose: (bool) print estimated export time to console. Default False
        :return: None
        """
        timestamp = time.time()

        # get data from device
        info = recording.get_channel_info(self.device.id, 'mc')
        n_data_points:int = int((info['to'] - info['from']) * info['sample_rate'])
        data = recording.get_channel_data(self.device.id, 'mc', 0, n_data_points)

        if verbose:
            print(f'exporting ... expected time: {n_data_points * 0.0000034} seconds')

        # USE NUMPY TO EXPORT CSV with format value,timestamp\n (written by ai)
        import numpy as np
        interval = data['interval']
        values = np.array(data['values'])
        # Generate timestamps using NumPy
        timestamps = np.arange(len(values)) * interval
        # Combine values and timestamps into a 2D array
        result = np.column_stack((values, timestamps))
        # Save to CSV
        header = "Value,Timestamp"
        np.savetxt(output_file_path, result, delimiter=',', header=header, comments='', fmt='%s')

        if verbose:
            print(f'exported {n_data_points} datapoints in {time.time() - timestamp} seconds')

    def export_last_n_recordings(self, output_dir:str, n:int):
        recordings = self.project.get_recordings()
        l = len(recordings)
        for i, r in enumerate(recordings[l-n:]): # reads the last n recordings in order
            filepath = os.path.join(output_dir, f'r{i}.csv')
            self.export_recording(r, filepath)

    def del_all_recordings(self):
        for r in self.project.get_recordings():
            r.delete()

if __name__ == '__main__': # for tests
    otii = Arc()

    otii.start_recording()
    time.sleep(6)
    otii.stop_recording()
    time.sleep(0.5)

    otii.start_recording()
    time.sleep(7)
    otii.stop_recording()
    time.sleep(0.5)

    # print(otii.get_last_recording_stats(1.5, 2))
    otii.disconnect()