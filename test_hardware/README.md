# `test_hardware`: Automated testing for enDAQ™ data recorders
The `test_hardware` folder contains tests which will automatically run on physical enDAQs. These tests check the functionality of certain enDAQ device commands and series of commands. Details on what each test is testing for can be found in their corresponding docstrings. This folder is still a **work in progress**, so some of the above-mentioned functionality may not be implemented yet. 

## `test_device.py`
This is a collection of tests meant to test the functionality of specific commands on physical enDAQ devices. These tests can be run on both W and S type enDAQs. 

### Manual Testing
If your computer is connected to an enDAQ with a **firmware version > 3.01.00**, these tests can be manually run using pytest:

```pytest .\test_device.py --device "S0000000" -s``` Replace `"S0000000"` with the serial number of your device.

If you are failing tests, running into errors, or want a more detailed view into the tests as they run, run this line instead:

```pytest .\test_device.py --device "S0000000" -s --verbose```

If you want to run your tests in a random order, first install pytest-random-order using `pip install pytest-random-order`, and then add the `--random-order` flag to one of the pytest command line examples above.

### RasPi Testing / Automatic Testing
**Automatic testing through GitHub Actions will only be available for approved MIDE users!**

The process of automatic testing is done with the help of a Raspberry Pi. First `ssh` into the RasPi. Next, activate the virtual environment located in the `endaq.device` repository called `testing_venv`. From there, automatic testing should be set up to run (**not yet implemented**). Manual testing through the RasPi is also set up.

#### Manual Testing with a RasPi
Navigate to the `testing_hardware` directory and then run `pytest test_device.py --device "S0000000" --raspi -s` to manually test on the RasPi. Replace `"S0000000"` with the serial number of your device. Optionally add the "--verbose" and "--random-order" flags to increase the printed output information and run the tests in a random order.

#### Automatic Testing with a RasPi
Not yet implemented.

#### GPIO Bug Fix
If upon running the test you get the following error, "RuntimeError: No access to /dev/mem.  Try running as root!", here's how to fix it. Run `ls -l /dev/gpiomem` in your terminal. If the output does not start with "crw-rw---- 1 root gpio", then run `sudo chown root:gpio /dev/gpiomem && sudo chmod g+rw /dev/gpiomem` which should fix it. Running `ls -l /dev/gpiomem` should now display the correct output. 

## `test_w_devices.py`
This is a collection of tests that are specific to W type enDAQs and their Wi-Fi capabilities. These tests will produce errors if run on S type devices.

### Manual Testing
All of the information described in the "`test_device.py` Manual Testing" section above applies to `test_w_devices.py` as well, with one exception: the serial number listed in the command line pytest code must begin with a **"W"** for the tests to run properly, as only W type enDAQs support the functions being run by these tests.

### Automatic Testing
Automatic testing is **not yet supported** for `test_w_devices.py`. Once it is, it will follow the same set up as for `test_device.py`, but with a W type enDAQ connected to the RasPi in place of an S type.