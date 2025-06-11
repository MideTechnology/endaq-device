# "Fake" recorders for testing

These are copies of system files from actual SlamStick and enDAQ recorders.
They can be identified and/or instantiated as `Recorder` objects using the
argument `strict=False`, which skips the filesystem checks that would
counterindicate they are recorders.

The directory names must match the device's part number, either entirely
or up to an underscore in the directory name. Additional information may
follow the underscore (e.g., the the device's firmware version). 
