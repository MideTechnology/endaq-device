"""
Automated tests for endaq.device.
"""
import endaq.device
from endaq.device import DeviceStatusCode as Status
from idelib.importer import importFile
import ebmlite
import pytest

from test_hardware.helper_functions.general_config import GeneralConfig

import time
import calendar
from datetime import datetime
from datetime import timezone as tz
import glob
import os
from pathlib import Path


class Payload:
    payload = ''

TODO = lambda name : pytest.skip(f"Test {name} has not yet been implemented")
# ================= TESTS ================= # 
# # Standard tests.
def test_standard_run(device_manager):
    """ Test a standard run of an enDAQ device."""
    # Set up; Confirm device is idle
    device = device_manager.device
    serial_number = device.serial
    
    device_manager.start_recording(Status.RECORDING)    
    assert device.serial == serial_number, "Did not reconnect to the same device."
    device_manager.stop_recording()

class TestAwait:
    """
    Tests the 4 await functions in the device's command library
    Note that some / all of these methods are second-hand tested in several of 
    the helper functions.
    """

    def test_await_disconnect(self, device_manager):
        """

        """
        device = device_manager.device

        disconnector = lambda: None if device.command.reset() else False
        #perform action that would cause a disconnect.
        assert device.command.awaitDisconnect(
            timeout = 30, 
            callback = disconnector
            ) == True
        device.command.awaitReconnect(timeout = 30)

    def test_await_dismount(self, device_manager):
        """
    
        """
        device = device_manager.device

        disconnector = lambda: None if device.command.startRecording() else False
        
        assert device.command.awaitDismount(
            timeout = 30,
            callback = disconnector,
        ) == True
        device.command.awaitReconnect(timeout = 30)
        device.command.stopRecording()
        device.command.awaitRemount(timeout = 30)
        device.command.awaitReconnect()

    def test_await_reconnect(self, device_manager):
        """
        Tests that waiting for reconnect when connected is near-instantaneous,
        and that commands can be sent when reconnected.
        """
        device = device_manager.device
        #ensuring it starts connected
        device.command.awaitReconnect(timeout = 10)
        assert device.command.awaitReconnect(timeout = 2) == True
        #the moment it reconnects, we can send a ping
        device.command.startRecording()
        device.command.awaitReconnect(timeout = 30)
        device.command.ping() #as long as it doesn't error, it "passes"
        #cleanup
        device.command.stopRecording()
        device.command.awaitRemount()


    def test_await_remount(self, device_manager):
        """
        Tests that waiting for a remount is near instantaneous when the device is
        remounted, and that the drive can be read when remounted.
        """
        device = device_manager.device
        #ensuring it starts connected
        device.command.awaitRemount(timeout = 10)
        assert device.command.awaitRemount(timeout = 2) == True
        #the moment it reconnects, we can send a ping
        device.command.startRecording()
        device.command.awaitReconnect(timeout = 30)
        device.command.stopRecording()
        device.command.awaitRemount(timeout = 30)
        device.command.awaitRemount(timeout = 2)

@pytest.mark.skip("TestVirtualAccuracy not implemented yet")
class TestVirtualAccuracy:
    """
    A series of tests used to test the validity of real device to Recorder conversion
    """
    def _new_rec(self, device_manager) -> endaq.device.Recorder:
        """
        
        """
        pytest.skip("_new_rec has not been implemented yet")
        device_manager.make_recording()
        #get the recording
        virt_path = ...
        with importFile(virt_path) as f:
            return endaq.device.fromRecording(f)

    def test_virtual_accuracy_channels(self, device_manager):
        device = device_manager.device
        virtual = self._new_rec(device_manager)
        ch = device.channels[80]
        assert device.getAccelRange(ch) == virtual.getAccelRange(ch)
        assert device.getAccelAxisChannels(ch) == virtual.getAccelAxisChannels(ch)


    def test_virtual_accuracy_cals(self, device_manager):
        """
        tests the accuracy of the calibration retrieval functions, both user
        and non-user generated. Note that this doesn't test anything embl related,
        that is in `test_virtual_accuracy_embl`
        """
        device = device_manager.device
        virtual = self._new_rec(device_manager=device_manager)

        for b in [False, True]:
            assert device.getCalDate(b) == virtual.getCalDate(b)
            assert device.getCalExpiration(b) == virtual.getCalExpiration(b)
            assert device.getCalPolynomials(b) == virtual.getCalPolynomials(b)
            assert device.getCalibration(b) == virtual.getCalibration(b)
    
    def test_virtual_accuracy_props(self, device_manager):
        device = device_manager.device
        virtual = self._new_rec(device_manager=device_manager)

        assert device.name == virtual.name
        assert device.partNumber == virtual.partNumber
        assert device.productName == virtual.productName
        #assert device.notes == virtual.notes TODO: bug?
        assert device.birthday == virtual.birthday
        assert device.firmware == virtual.firmware
        assert device.firmwareVersion == virtual.firmwareVersion
        assert device.chipId == virtual.chipIdV
    
    def test_virtual_accuracy_funcs(self, device_manager):
        """
        tests the methods on 
        """
        device = device_manager.device
        virtual = self._new_rec(device_manager=device_manager)
        
        assert device.getSensors() == virtual.getSensors()
        assert device.getProperties() == virtual.getProperties()
        assert device.getManifest() == virtual.getManifest()

    def test_virtual_accuracy_embl(self, device_manager):
        """
        tests the accuracy of the calibration tests based on the ebml files
        """
        TODO('test_virtual_accuracy_embl')

def test_write_user_cal(device_manager):
    TODO('test_write_user_cal')

# This test only works if looped in sequential order. Random order is disabled
# for this reason.
@pytest.mark.random_order(disabled=True)
@pytest.mark.parametrize("index", range(1, 31))
def test_ping_payload(device_manager, index):
    """ 
    Tests that 'ping()' returns the input payload for a range of bytearray sizes.

    :param index: parameterized index of payload bitarray length.
    """
    # Connect to device
    device = device_manager.device

    # Ensure the payload begins empty at start of loop
    if index == 1:
        Payload.payload == ''

    # Increase the length of the payload and send it to ping()
    Payload.payload += chr(index)
    device.command.awaitReconnect(30)
    returned_payload = device.command.ping(bytearray(Payload.payload, 'utf-8'))
    print(f"\n{bytearray(Payload.payload, 'utf-8')} <-- Payload size {index}"
          f"\n{returned_payload} <-- Returned Payload")

    # Confirm that ping() returns the same thing it was sent
    assert returned_payload == bytearray(
        Payload.payload, 'utf-8'), f"ping() failed on size {index}."

def test_property_accuracy(device_manager):
    """
    Tests that device properties of a "Real" Recorder are correct.
    """
    
    device = device_manager.device
    #for sake of modularity, information like birthday / channels aren't
    #checked.
    assert device.available and (device.available == device.config.available)
    assert device.config.name == device.name
    assert device.config.notes == device.notes
    assert device.canRecord
    assert device.hasConfigInterface
    assert device.command is not None and device.hasCommandInterface
    assert not device.isVirtual

def test_virtual_accuracy(device_manager,):
    """
    Tests that fields consistent between Virtual and "Real" recorders 
    are accurate.
    """
    device = device_manager.device
    device_manager.make_recording()
    device.command.awaitRemount()
    rec_path = max(
        glob.glob(str(Path(device.path+f"/Data/{getattr(device.config, 'recordingDir', 'RECORD')}/*.IDE"))),
        key = os.path.getctime
    )
    ide_file = importFile(rec_path)
    virtual = endaq.device.Recorder.fromRecording(ide_file)


@pytest.mark.tty
def test_unplug_device(device_manager):
    """
    Tests methods that produce different results when a device 
    is plugged in / unplugged.
    Note that this test assumes only one device is plugged in, and will fail otherwise
    """
    device = device_manager.device
    config_dict = {"WifiEnable": 0}
    config = GeneralConfig(**config_dict)
    if config.set_configs(device, quick_config=True):
        device.config.applyConfig()
    for usb_on, num_connected in iter([(False, 0), (True, 1)]):    
        device_manager.hw_interface.set_usb(usb_on)
        time.sleep(10) #TODO: maybe awaitDisconnect / reconnect works here?
        assert (len(endaq.device.getDevices()) == num_connected
               ), f"getDevices detected {endaq.device.getDevices()}, when only {num_connected} is present"
        assert (len(endaq.device.getDeviceList()) == num_connected
               ), f"getDeviceList detected {endaq.device.getDevices()}, when only {num_connected} is present"

def test_get_devices_unmounted_recording(device_manager):
    """Tests that getDevices correctly reads a recording device as unmounted""" 
    device = device_manager.device
    device_sn = device.serial

    device_manager.start_recording()
    mounted_devices = endaq.device.getDevices(unmounted=False)
    serial_numbers = [device.serial for device in mounted_devices]
    assert device_sn not in serial_numbers, "Device was returned while recording." 
    device_manager.stop_recording()

def test_start_recording_wait(device_manager) :
    """ 
    Tests that 'startRecording()' returns faster than the default case when 'wait=False'.
    """
    device = device_manager.device

    # Running SR with wait=False; recording how long it takes; stop rec.
    no_wait_start_time = time.time()
    device.command.startRecording(wait=False)
    no_wait_end_time = time.time()
    no_wait_dt = no_wait_end_time - no_wait_start_time

    device_manager.stop_recording()

    device = device_manager.device

    # Running SR with wait=True; recording how long it takes; stop rec.
    default_start_time = time.time()
    device.command.startRecording()
    default_end_time = time.time()
    default_dt = default_end_time - default_start_time
    device_manager.stop_recording()
    # Verify the wait=False case ran quicker than the wait=True case.
    print("wait=False:", no_wait_dt,
            "wait=True:", default_dt)
    assert (no_wait_dt < default_dt
            ), "Default returned quicker than when wait=False."

                
# # Device change tests 
def test_set_config(device_manager):
    """
    Test that basic config info is stored across reboots. 
    """
    device = device_manager.device
    
    old_name = device.name
    test_name = f"T{time.time()}"
    
    device.config.items[0x8FF7F].value = test_name
    
    device.config.applyConfig()
    device.command.reset()
    
    device_manager.dememomize_device()
    dev = device_manager.device
    
    initial_dev_name = dev.name
    dev.refresh()
    reload_dev_name = dev.config.items[0x8FF7F].value
    
    dev.config.items[0x8FF7F].value = old_name
    dev.config.applyConfig()
    error_list = []
    if test_name != initial_dev_name:
        error_list.append(f"Weird, reloaded device name did not reflect test name. Expected {test_name} got "
                          f"{initial_dev_name}. Initial name was {old_name}")
    if test_name != reload_dev_name:
        error_list.append(f"After rebooting the device, it did not keep the newly configured name. This probably means "
                          f"config.cfg was not flushed out to the device. Try mounting with the 'flush' option, or "
                          f"waiting up to 6 seconds between applying config and disconnecting. Expected {test_name} got "
                          f"{reload_dev_name}, initial name was {old_name}")
    assert len(error_list) == 0, "\n".join(error_list)

def test_bad_end(device_manager):
    """
    Tests that calling end in unexpected cases (explained case by case in inline comments)
    is handled properly.
    In the case that the firmware version is incompatible, this test will be skipped
    """
    #TODO: make sure that the firmware is right. lower firmware versions will have the raspi stop
    #      recording, which wouldn't raise the error
    #attempts to call end before start is called.
    with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
        device_manager.stop_recording()
    assert str(excinfo.value) == "[ERR_INVALID_COMMAND -20] Badly formed command"
    #attempts to call end after already calling end
    device_manager.make_recording(Status.RECORDING)

    with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
        device_manager.stop_recording()
    assert str(excinfo.value) == "[ERR_INVALID_COMMAND -20] Badly formed command"


sample_datetime = datetime(2000,3,14,15,2,30, tzinfo=tz.utc)
sample_dt_out = sample_datetime.timestamp()
sample_struct_time = time.gmtime()

@pytest.mark.parametrize('time_value, expected_out', [
    (sample_datetime.timestamp(), sample_dt_out), #float,
    (int(sample_datetime.timestamp()), sample_dt_out), #int,
    (sample_datetime, sample_dt_out), #datetime
    (sample_struct_time, calendar.timegm(sample_struct_time)), #struct_time
])
def test_set_time(device_manager, time_value, expected_out):
    """
    Tests that the different supported time representations work as intended.
    """
    TIME_TOLERANCE = 1
    device = device_manager.device
    start_time = time.time()
    device.command.setTime(time_value)
    elapsed_time = time.time() - start_time
    #NOTE: minimum time is Jan 1 2000. anything below will snap to it.
    assert -1 * TIME_TOLERANCE <= device.command.getTime()[1] - (expected_out + elapsed_time) <= TIME_TOLERANCE
    device.command.setTime()
    
class TestLock:
    """
    A collection of tests based on the set of `Lock` functions in a Recorder's Command Interface
    """
    def test_bad_lockID(self, device_manager):
        """
        Tests that the correct error messages are shown when inputting incompatible lock ids.
        """
        device = device_manager.device
        with pytest.raises(TypeError) as excinfo:
            device.command.setLockID(1)
        assert str(excinfo.value) == "Cannot encode int 1 as binary"
        with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
            device.command.setLockID("1")
        assert str(excinfo.value) == "[ERR_BAD_LOCK_ID -21] Command Lock ID invalid or already set"
    
    def test_standard_lock_run(self, device_manager):
        """
        tests that the lock-based methods work as intended when used in a typical manner.
        """
        device = device_manager.device
        assert device.command.setLockID()
        with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
            device.command.startRecording()
        assert str(excinfo.value) == "[ERR_BAD_LOCK_ID -21] Command Lock ID invalid or already set"
        lockID = device.command.getLockID()
        assert device.command.clearLockID(lockID)
        device_manager.make_recording()

    def test_no_lock_props(self, device_manager):
        """Tests that lock-based properties work as intended without an active lock id set."""
        device = device_manager.device
        assert device.command.getLockID() is None
        assert device.command.isLocked() == (False, False) 
        #tests that clearing non-existant lockID doesn't break
        assert device.command.clearLockID()

#TODO: find compatible value for every object.
def _change_cfg_value(cfg_item: endaq.device.config.ConfigItem):
    """
    Finds and applies a value that is valid and different than the existing value in the 
    given config item.
    Note that this function does not guarentee that `device.config.applyConfig()` will not error,
    only ensuring that making a change doesn't error. Types may be incorrect due to this assumption.
    """
    num_options = len(cfg_item.options)
    if num_options <= 1: 
        cfg_item.value = 30 if cfg_item.value != 30 else 0
    else: 
        cfg_item.value = next((k for k, _ in cfg_item.options.items() if cfg_item.value != k), None)

def test_get_revert_changes(device_manager):
    """
    Tests that all config items can be modified, and all show up when calling `getChanges()`.
    Additionally tests that `device.config.revert()` reverts all of the changes
    made.
    """
    device = device_manager.device
    assert len(device.config.getChanges()) == 0
    rec_item = device.config.items[917375] 
    rec_item.value = 60 if rec_item.value != 60 else 120
    assert len(device.config.getChanges()) == 1
    device.config.revert()
    assert len(device.config.getChanges()) == 0


def test_is_enabled(device_manager):
    device = device_manager.device
    ch80 = device.channels[80]
    device.config.enableChannel(ch80, enabled=True)
    assert device.config.isEnabled(ch80) == True
    device.config.enableChannel(ch80, enabled=False)
    assert device.config.isEnabled(ch80) == False
    
def test_set_get_trigger(device_manager):
    """
    Tests that the triggers set in `getTrigger` is reflected in getTrigger
    """
    device = device_manager.device  
    
    ch80 = device.channels[80]
    device.config.setTrigger(ch80, enabled=True, high = 10)
    device.config.applyConfig()
    device.config.getTrigger(ch80) == {'enabled': 1, 'high': 10}
    
    device.config.setTrigger(ch80, enabled=False)
    device.config.applyConfig()
    device.config.getTrigger(ch80) == {'enabled': 0, 'high': 10}

def test_get_config_values(device_manager):
    """
    Tests that getConfigValues reflects the values present in `device.config.items`.
    """
    device = device_manager.device
    config_vals = device.config.getConfigValues()
    for k,v in config_vals.items():
        if k in device.config.items: 
            assert device.config.items[k].value == v

@pytest.mark.parametrize('sample_rate, is_valid', [
    *[(k, True) for k in [4000, 2000, 1000, 500, 250, 125, 63, 32, 16]],
    *[(k, False) for k in [3000, 1500, 780, 200]]
])
def test_sample_rate(device_manager, sample_rate, is_valid):
    """
    Tests that applying all of the allowed sample rates work, and non-valid 
    sample_rates throw the correct error.
    """
    device = device_manager.device
    if is_valid:
        device.config.setSampleRate(device.channels[80], sample_rate)
        assert device.config.getSampleRate(device.channels[80]) == sample_rate
    else:
        with pytest.raises(ValueError):
            device.config.setSampleRate(device.channels[80], sample_rate)


@pytest.mark.parametrize('attr_name, attr_id, attr_value, expected_out', [
    ('retrigger', 0xEFF7F, 1, 1),
    ('recordingStartTime', 0xFFF7F, sample_datetime.timestamp(), sample_datetime),
    ('recordingSizeLimit', 0x11FF7F, 1, 1),
    ('recordingPrefix', 0x15FF7F, 'recTMP', 'recTMP'),
    ('recordingDir', 0x14FF7F, 'recTMP', 'recTMP'),
    ('notes', 0x9FF7F, 'tmp', 'tmp'),
    ('name', 0x8FF7F, 'tmp', 'tmp'),
    ('buttonMode', 0x10FF7F, 1, 1)
])
def test_config_props(device_manager, attr_name, attr_id, attr_value, expected_out):
    """
    tests that the properties in `device.config` match the values that are assigned from the config.
    """
    device = device_manager.device

    cfg_item = device.config.items[attr_id]
    cfg_item.value = attr_value
    device.config.applyConfig()
    assert getattr(device.config, attr_name) == expected_out
    
   