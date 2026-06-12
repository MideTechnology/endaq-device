import time
import pytest
from datetime import datetime, timezone as tz
"""
A test file dedicated to testing the communication between
the config interface and the device.
"""

@pytest.mark.skip("known bug")
def test_set_config(session_manager):
    """
    Test that basic config info is stored across reboots. 
    """
    device = session_manager.device
    
    original_name = device.name
    updated_name = f"T{time.time()}"
    
    device.config.items[0x8FF7F].value = updated_name
    
    device.config.applyConfig()
    device.command.reset()
    
    session_manager.dememoize_device()
    dev = session_manager.device
    
    pre_refresh_update = dev.name
    dev.refresh()
    post_refresh_update = dev.config.items[0x8FF7F].value
    
    dev.config.items[0x8FF7F].value = original_name
    dev.config.applyConfig()
    error_list = []
    if updated_name != pre_refresh_update:
        error_list.append(f"Weird, reloaded device name did not reflect test name. Expected {updated_name} got "
                          f"{pre_refresh_update}. Initial name was {original_name}")
    if updated_name != post_refresh_update:
        error_list.append(f"After rebooting the device, it did not keep the newly configured name. This probably means "
                          f"config.cfg was not flushed out to the device. Try mounting with the 'flush' option, or "
                          f"waiting up to 6 seconds between applying config and disconnecting. Expected {updated_name} got "
                          f"{post_refresh_update}, initial name was {original_name}")
    assert len(error_list) == 0, "\n".join(error_list)

def test_get_revert_changes(session_manager):
    """
    Tests that all config items can be modified, and all show up when calling `getChanges()`.
    Additionally tests that `device.config.revert()` reverts all of the changes
    made.
    """
    device = session_manager.device
    assert len(device.config.getChanges()) == 0
    rec_item = device.config.items[917375] 
    rec_item.value = 60 if rec_item.value != 60 else 120
    assert len(device.config.getChanges()) == 1
    device.config.revert()
    assert len(device.config.getChanges()) == 0


def test_is_enabled(session_manager):
    device = session_manager.device
    ch80 = device.channels[80]
    device.config.enableChannel(ch80, enabled=True)
    assert device.config.isEnabled(ch80) == True
    device.config.enableChannel(ch80, enabled=False)
    assert device.config.isEnabled(ch80) == False
    
def test_set_get_trigger(session_manager):
    """
    Tests that the triggers set in `getTrigger` is reflected in getTrigger
    """
    device = session_manager.device  
    
    ch80 = device.channels[80]
    device.config.setTrigger(ch80, enabled=True, high = 10)
    device.config.applyConfig()
    device.config.getTrigger(ch80) == {'enabled': 1, 'high': 10}
    
    device.config.setTrigger(ch80, enabled=False)
    device.config.applyConfig()
    device.config.getTrigger(ch80) == {'enabled': 0, 'high': 10}

def test_get_config_values(session_manager):
    """
    Tests that getConfigValues reflects the values present in `device.config.items`.
    """
    device = session_manager.device
    config_vals = device.config.getConfigValues()
    for k,v in config_vals.items():
        if k in device.config.items: 
            assert device.config.items[k].value == v

@pytest.mark.parametrize('sample_rate, is_valid', [
    *[(k, True) for k in [4000, 2000, 1000, 500, 250, 125, 63, 32, 16]],
    *[(k, False) for k in [3000, 1500, 780, 200]]
])
def test_sample_rate(session_manager, sample_rate, is_valid):
    """
    Tests that applying all of the allowed sample rates work, and non-valid 
    sample_rates throw the correct error.
    """
    device = session_manager.device
    if is_valid:
        device.config.setSampleRate(device.channels[80], sample_rate)
        assert device.config.getSampleRate(device.channels[80]) == sample_rate
    else:
        with pytest.raises(ValueError):
            device.config.setSampleRate(device.channels[80], sample_rate)


sample_datetime = datetime(2000,3,14,15,2,30, tzinfo=tz.utc)
@pytest.mark.parametrize('attr_name, attr_id, attr_type', [
    ('retrigger', 0xEFF7F, "int"),
    ('recordingSizeLimit', 0x11FF7F, "int"),
    ('recordingPrefix', 0x15FF7F, "str"),
    ('recordingDir', 0x14FF7F, "str"),
    ('notes', 0x9FF7F, "str"),
    ('name', 0x8FF7F, "str"),
    ('buttonMode', 0x10FF7F, "int")
])
def test_config_props(session_manager, attr_name, attr_id, attr_type):
    """
    tests that the properties in `device.config` match the values that are assigned from the config.
    """
    device = session_manager.device
    cfg_item = device.config.items[attr_id]
    if attr_type == "int":
        #the config we set for button mode is 0, so this will increment to 1.
        #a different button mode value will break it.
        new_val = (cfg_item.value or 0) + 1
    elif attr_type == "str":
        new_val = (cfg_item.value or "") + "NEW"
    cfg_item.value = new_val
    device.config.applyConfig()
    assert getattr(device.config, attr_name) == new_val
    
def test_config_start_time_props(session_manager):
    """
    A variation on `test_config_props` for recordingStartTime, as it's 
    validity checking is slightly different
    """
    pytest.skip("test_config_start_time_props not implemented yet")
    ...
