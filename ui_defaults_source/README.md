_Note: Unless you're a developer supporting a new model of data recorder,
you should probably ignore this directory._

This directory contains the raw binary EBML files for default `CONFIG.UI` data,
from which the modules in `endaq.device.ui_defaults` are manually generated.
This data is used for device configuration for cases in which there is no
actual ConfigUI data (primarily 'virtual' devices instantiated from recordings
or real devices with very old firmware). 

Only the modules in `endaq.device.ui_defaults` are part of the published
package; these source .UI files are not.

The file `make_defaults.py` contains some functions to help generate Python
modules from the `.UI` files. It can also be run from the command line as a 
utility.
