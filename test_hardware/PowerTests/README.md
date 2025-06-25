# `PowerTests`: Using the Otii for automated enDAQ™ device testing

The `PowerTests` directory is taken from the `firmware_tests` repo (with some minor modifications) to aid in running automated enDAQ device tests.

## `setupTeardown()`
**Otii controlled enDAQ reboot not yet implemented!**

The Otii controls how the enDAQ is being powered in the automated testing setup. **Once implemented**, the Otii will reboot the enDAQ between each test as a part of the `setupTeardown()` pytest fixture function present in both `test_device.py` and `test_w_devices.py`. This will help to ensure that each test is run without the interference of any other test through leftover configurations, commands, statuses, etc.

## `select_otii_device.py`
When run, this file connects to and configures the connected Otii device.

## `Instruments`
This directory is used for configuring and commanding the Otii and enDAQ as well as performing low-level actions via Serial on the Otii Power Board.

## `Orchestration.py`
Contains high level tools for taking enDAQ power measurements.