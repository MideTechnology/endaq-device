# `endaq.device`: Represent, control, and configure enDAQ™ data recorders
[![PyPI Latest Release](https://img.shields.io/pypi/v/endaq-device.svg)](https://pypi.org/project/endaq-device/) ![example workflow](https://github.com/MideTechnology/endaq-device/actions/workflows/unit-tests.yml/badge.svg)

`endaq.device` (formerly `endaqlib`) provides a means of representing, accessing, configuring
and controlling [enDAQ™ data
recorders](https://endaq.com/collections/endaq-shock-recorders-vibration-data-logger-sensors).
It also supports legacy SlamStick™ devices (X, C, and S).

## Installation

The `endaq-device` package is [available on
PyPI](https://pypi.org/project/endaq-device/), and can be installed via
`pip`:

    pip install endaq-device

For the most recent features that are still under development, you can
also use <span class="title-ref">pip</span> to install endaq directly
from [the GitHub
repository](https://github.com/MideTechnology/endaq-device/):

    pip install git+https://github.com/MideTechnology/endaq-device.git@develop

Note: While `endaq-device` installs into the same `endaq` 'namespace' as
[endaq-python](https://docs.endaq.com/en/latest/index.html), it is
otherwise separate; the two packages are not interdependent, and one can
be installed without the other. The packages do distinctly different
things, and have very different use-cases. However, both packages (and any
future `endaq.*` packages) should be installed in the same location
(i.e., both installed for the current user, or both installed 'for all users',
*not* a combination). If you receive an `ImportError` trying to import 
`endaq.device`, you may need to remove and reinstall `endaq.device` (and/or 
other `endaq` packages).

## Documentation
*Note: the documentation is currently a work in progress.*

The docs for this package can be found [here](https://mide-technology-endaq-device.readthedocs-hosted.com/en/latest/).

## License

The endaq-python repository is licensed under the MIT license. The full text can be found in the [LICENSE file](https://github.com/MideTechnology/endaq-python/blob/main/LICENSE).
