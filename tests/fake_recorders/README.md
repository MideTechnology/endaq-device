# "Fake" recorders for testing

These are copies of system files from actual SlamStick and enDAQ recorders.
They can be identified and/or instantiated as `Recorder` objects using the
argument `strict=False`, which skips the filesystem checks that would
counterindicate they are recorders.

The directory names must match the device's part number, either entirely
or up to an underscore in the directory name. Additional information may
follow the underscore (e.g., the the device's firmware version).

Important: Because testing may run from a case-sensitive filesystem (e.g.,
most Linux systems), be sure that the contents of `SYSTEM/DEV` all have
uppercase filenames (`DEVINFO`, `DEVPROPS`, `MANIFEST`, `SYSCAL`, `USERPG*`,
etc.) when creating a new fake device. Some versions of the STM32 firmware
are inconsistent with the case of filenames, as the device's native FS is
case-insensitive.
