"""
Tests the communication between the command interface and the device
"""

import endaq.device
from endaq.device import DeviceStatusCode as Status
import pytest

import time
import calendar
from datetime import datetime, timezone as tz


def test_standard_run(session_manager):
    """ Test a standard run of an enDAQ device."""
    # Set up; Confirm device is idle
    device = session_manager.device
    serial_number = device.serial
    
    session_manager.start_recording(Status.RECORDING)    
    assert device.serial == serial_number, "Did not reconnect to the same device."
    session_manager.stop_recording()

class TestAwait:
    """
    Tests the 4 await functions in the device's command library
    Note that some / all of these methods are second-hand tested in several of 
    the helper functions.
    """

    def test_await_disconnect(self, session_manager):
        """

        """
        device = session_manager.device

        disconnector = lambda: None if device.command.reset() else False
        #perform action that would cause a disconnect.
        awaitOut = device.command.awaitDisconnect(
            timeout = 30, 
            callback = disconnector
            ) == True

        assert awaitOut
        device.command.awaitReconnect(timeout = 30)
    
    #wifi devices can never dismount because they aren't mounted
    @pytest.mark.serial
    def test_await_dismount(self, session_manager):
        """
    
        """
        device = session_manager.device

        disconnector = lambda: None if device.command.startRecording() else False
        
        assert device.command.awaitDismount(
            timeout = 30,
            callback = disconnector,
        ) == True
        device.command.awaitReconnect(timeout = 30)
        device.command.stopRecording()
        device.command.awaitRemount(timeout = 30)
        device.command.awaitReconnect()

    def test_await_reconnect(self, session_manager):
        """
        Tests that waiting for reconnect when connected is near-instantaneous,
        and that commands can be sent when reconnected.
        """
        device = session_manager.device
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

    #wifi devices can never remount because they aren't mounted
    @pytest.mark.serial
    def test_await_remount(self, session_manager):
        """
        Tests that waiting for a remount is near instantaneous when the device is
        remounted, and that the drive can be read when remounted.
        """
        device = session_manager.device
        #ensuring it starts connected
        device.command.awaitRemount(timeout = 10)
        assert device.command.awaitRemount(timeout = 2) == True
        #the moment it reconnects, we can send a ping
        device.command.startRecording()
        device.command.awaitReconnect(timeout = 30)
        device.command.stopRecording()
        device.command.awaitRemount(timeout = 30)
        device.command.awaitRemount(timeout = 2)

# This test only works if looped in sequential order. Random order is disabled
# for this reason.
@pytest.mark.random_order(disabled=True)
@pytest.mark.parametrize("index", range(1, 31))
def test_ping_payload(session_manager, index):
    """ 
    Tests that 'ping()' returns the input payload for a range of bytearray sizes.

    :param index: parameterized index of payload bitarray length.
    """
    # Connect to device
    device = session_manager.device

    payload = "".join([chr(i) for i in range(index)])
    device.command.awaitReconnect(30)
    returned_payload = device.command.ping(bytearray(payload, 'utf-8'))
    print(f"\n{bytearray(payload, 'utf-8')} <-- Payload size {index}"
          f"\n{returned_payload} <-- Returned Payload")

    # Confirm that ping() returns the same thing it was sent
    assert returned_payload == bytearray(
        payload, 'utf-8'), f"ping() failed on size {index}."
    
def test_start_recording_wait(session_manager) :
    """ 
    Tests that 'startRecording()' returns faster than the default case when 'wait=False'.
    """
    device = session_manager.device

    # Running SR with wait=False; recording how long it takes; stop rec.
    no_wait_start_time = time.time()
    device.command.startRecording(wait=False)
    no_wait_end_time = time.time()
    no_wait_dt = no_wait_end_time - no_wait_start_time

    session_manager.stop_recording()

    device = session_manager.device

    # Running SR with wait=True; recording how long it takes; stop rec.
    default_start_time = time.time()
    device.command.startRecording()
    default_end_time = time.time()
    default_dt = default_end_time - default_start_time
    session_manager.stop_recording()
    # Verify the wait=False case ran quicker than the wait=True case.
    print("wait=False:", no_wait_dt,
            "wait=True:", default_dt)
    assert (no_wait_dt < default_dt
            ), "Default returned quicker than when wait=False."

def test_bad_end(session_manager):
    """
    Tests that calling end in unexpected cases (explained case by case in inline comments)
    is handled properly.
    In the case that the firmware version is incompatible, this test will be skipped
    """
    #TODO: make sure that the firmware is right. lower firmware versions will have the raspi stop
    #      recording, which wouldn't raise the error
    #attempts to call end before start is called.
    with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
        session_manager.stop_recording()
    assert str(excinfo.value) == "[ERR_INVALID_COMMAND -20] Badly formed command"
    #attempts to call end after already calling end
    session_manager.make_recording(Status.RECORDING)

    with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
        session_manager.stop_recording()
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
def test_set_time(session_manager, time_value, expected_out):
    """
    Tests that the different supported time representations work as intended.
    """
    TIME_TOLERANCE = 1
    device = session_manager.device
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
    def test_bad_lockID(self, session_manager):
        """
        Tests that the correct error messages are shown when inputting incompatible lock ids.
        """
        device = session_manager.device
        with pytest.raises(TypeError) as excinfo:
            device.command.setLockID(1)
        assert str(excinfo.value) == "Cannot encode int 1 as binary"
        with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
            device.command.setLockID("1")
        assert str(excinfo.value) == "[ERR_BAD_LOCK_ID -21] Command Lock ID invalid or already set"
    
    def test_standard_lock_run(self, session_manager):
        """
        tests that the lock-based methods work as intended when used in a typical manner.
        """
        device = session_manager.device
        assert device.command.setLockID()
        with pytest.raises(endaq.device.exceptions.CommandError) as excinfo:
            device.command.startRecording()
        assert str(excinfo.value) == "[ERR_BAD_LOCK_ID -21] Command Lock ID invalid or already set"
        lockID = device.command.getLockID()
        assert device.command.clearLockID(lockID)
        session_manager.make_recording()

    def test_no_lock_props(self, session_manager):
        """Tests that lock-based properties work as intended without an active lock id set."""
        device = session_manager.device
        assert device.command.getLockID() is None
        assert device.command.isLocked() == (False, False) 
        #tests that clearing non-existant lockID doesn't break
        assert device.command.clearLockID()

