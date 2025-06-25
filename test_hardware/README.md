# `test_hardware`: Automated testing for enDAQ™ data recorders
The `test_hardware` folder contains tests which will automatically run on physical enDAQs upon the completion of a specific GitHub action (such as pushing or opening a pull request) by an approved user. These tests check the functionality of certain enDAQ device commands and series of commands. Details on what each test is testing for can be found in their corresponding docstrings. This folder is still a **work in progress**, so some of the above-mentioned functionality may not be implemented yet. While there are plans to adapt these tests based on the firmware of the device it is run on, they are currently only meant to be run on any **firmware version 3.01.00** or more recent.

## `test_device.py`
This is a collection of tests meant to test the functionality of specific commands on physical enDAQ devices. These tests can be run on both W and S type enDAQs. 

### Manual Testing
If your computer is connected to an enDAQ, these tests can be manually run using pytest:

```pytest .\test_device.py --device "S0000000"``` Replace `"S0000000"` with the serial number of your device.

If you are failing tests, running into errors, or want a more detailed view into the tests as they run, run this line instead:

```pytest .\test_device.py --device "S0000000" -s -r w --verbose```

If you want to run your tests in a random order, first install pytest-random-order using `pip install pytest-random-order`, and then add the `--random-order` flag to one of the pytest command line examples above.

### Automatic Testing
**Automatic testing through GitHub Actions will only work for approved MIDE users!**

The process of automatic testing is done with the help of a Raspberry Pi and an Otii (read more about Otiis in `PowerTests/README.md`). If not running directly on the RasPi, first `ssh` into the RasPi. Next activate the virtual environment located in the `endaq.device` repository called `testing_venv`. Next, begin running the Otii by running `python .\PowerTests\select_otii_device.py s -t "60"`. From there, automatic testing should be set up to run every time an authorized user completes a specific git action (**not yet implemented**). Manual testing through the RasPi is also set up.

## `test_w_devices.py`
This is a collection of tests that are specific to W type enDAQs and their wifi capabilities. These tests will produce errors if run on S type devices.

### Manual Testing
All of the information described in the "`test_device.py` Manual Testing" section above applies to `test_w_devices.py` as well, with one exception: the serial number listed in the command line pytest code must begin with a **"W"** for the tests to run properly, as only W type enDAQs support the functions being run by these tests.

### Automatic Testing
Automatic testing is **not yet supported** for `test_w_devices.py`. Once it is, it will follow the same set up as for `test_device.py`, but with a W type enDAQ connected to the Otii and RasPi in place of an S type.