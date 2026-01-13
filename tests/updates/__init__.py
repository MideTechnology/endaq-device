"""
Device update files (firmware and userpage)

This directory contains a selection of test firmware and 'userpage' update
files for use with the fake recorders.

DO NOT attempt to use these on actual hardware! Some have been
deliberately damaged, others may harm real hardware.
"""

import os.path
from glob import glob

UPDATE_ROOT = os.path.realpath(os.path.dirname(__file__))
FIRMWARE_ROOT = os.path.join(UPDATE_ROOT, 'Firmware')
USERPAGE_ROOT = os.path.join(UPDATE_ROOT, 'Userpages')

USERPAGES = glob(os.path.join(USERPAGE_ROOT, 'userpage_*.bin'))
FIRMWARE_PKG = []
FIRMWARE_BIN = []

for root, dirs, files in os.walk(FIRMWARE_ROOT):
    dots = [d for d in dirs if d.startswith('.')]
    for d in dots:
        dirs.remove(d)

    FIRMWARE_PKG.extend(os.path.join(root, f) for f in files if f.endswith('.pkg'))
    FIRMWARE_BIN.extend(os.path.join(root, f) for f in files if f.endswith('.bin'))

FIRMWARE_ALL = FIRMWARE_PKG + FIRMWARE_BIN
FIRMWARE_PKG_ENCRYPTED = [f for f in FIRMWARE_PKG if 'encrypted' in f]
FIRMWARE_PKG_UNENCRYPTED = [f for f in FIRMWARE_PKG if 'encrypted' not in f]

