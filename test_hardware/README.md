# `test_hardware`: Automated testing for enDAQ™ data recorders
The `test_hardware` folder in `endaq.device` is used to test the communication between a physical enDAQ device and a computer.
Any testing that doesn't explicitly require a device can be found in the `tests` folder. 

## Command Line Arguments
These tests are run through pytest, which supports flags for testing customizability. These flags are ordered in importance.

### device
the `-D` or `--device` flag is a **required** flag that sets the serial number of the device being tested, including the first letter designating the device type.

### pytest flags
`-s` and `--verbose` are built in commands to pytest, that serve. `-s` is used to see 

Other flags that are native to pytest, such as `-k`, `--pdb`, `-x`, can also be used is desired.

For more information about these flags, refer to pytest documentation.

### raspi
the `-R` or `--raspi` flag designates the use of an in-house raspberry pi unit. 

When using a raspi, ensure that the device is plugged into the top-most port.

### no_tty
some tests require interaction with the device, either done through `--raspi` or a human. `--no_tty` disables the use for human-interaction, while still being able to see the output through `-s`. 

This flag has no effect if `--raspi` is enabled.

> If you are testing a device with firmware < 3.01.00, it is **highly** recommended to not use this option. Older firmwares require interaction to stop recording, which can cause issues if --no_tty is enabled.

### random-order
`random-order` is a 

### rerun
TODO
## Manual Testing
If your computer is connected to an enDAQ with a **firmware version > 3.01.00**, these tests can be manually run using pytest:

To manually run a test, use 
```
python -m pytest
```
with the flags mentioned in the preivous section. To specify files, add their 
directory to the command line. eg, for a test file named Foo and Bar
```
python -m pytest ./Foo ./Bar
```

```pytest .\test_device.py --device "S0000000" -s --verbose```

If you want to run your tests in a random order, first install pytest-random-order using `pip install pytest-random-order`, and then add the `--random-order` flag to one of the pytest command line examples above.

In the current state of testing, there is an ocassional serial-based error, ocassionally causing test failures due to TODO. It is highly encouraged to install pytest-rerunfailures using `pip install pytest-rerunfailures`, and add the following flags

- `--reruns 10` to rerun the failed tests 
- `--rerun-exepct AssertionError` to rerun the inconsistent failing tests
- `--reruns-delay 30` to let the resync and clear any issues.

All properties tested are checked using `assert`, so any non-`AssertionError` Exceptions are not being tested. Any tests written should follow this pattern, and try-catch statements should be used in case of any expected errors.
## Automatic Testing
> **Automatic testing through GitHub Actions will only be available for approved MIDE users!**

For automatic testing, first configure and enable the device as a github local
runner. Refer to internal documentation if more information is needed.

With this enabled, on the `endaq_device` Repo, go to `actions > Unit test on push and PR`
and choose the latest commit that has the test_hardware to test. 

Note that the yaml file has information specific to the device being tested, it may be necessary to update it to run properly.

## Bug Fixes / FAQ

### Raspi device not found / Raspi Test failing
This subsection is only relevant to in-house raspberry pi's with the 
custom hat.

If testing manually, there is a chance that the USB on hat has not been enabled. This can be fixed by running the following command
```
python ./test_hardware/helper_functions/raspi_endaq_controller -u On
```
Adjusting based on the current path of your terminal. 

Additionally, confirm that the enDAQ device is plugged into the port in the raspberry pi's hat, otherwise, the device will not sucessfully plug / unplug when prompted to.
### GPIO Bug Fix
If upon running the test you get the following error, "RuntimeError: No access to /dev/mem.  Try running as root!", here's how to fix it. Run `ls -l /dev/gpiomem` in your terminal. If the output does not start with "crw-rw---- 1 root gpio", then run `sudo chown root:gpio /dev/gpiomem && sudo chmod g+rw /dev/gpiomem` which should fix it. Running `ls -l /dev/gpiomem` should now display the correct output. 

### Sudo may be required
This subsection is specific to linux.

When running sudo, linux enviornments ignore the virtual environments (venv) pathing. To fix this, we call python straight from the venv.
Assuming a venv named `.venv`, run

```
sudo .venv/bin/python -m pytest ...
```
with the wanted parameters.