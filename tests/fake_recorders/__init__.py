"""
Fake recorders for testing.

Directory names should match the part number of the device their contents
emulate. Additional information can be added to the directory name after
an underscore (e.g., hardware revision differences, different MCU, etc.).
"""
import os.path

RECORDERS_ROOT = os.path.realpath(os.path.dirname(__file__))
RECORDER_PATHS = [os.path.join(RECORDERS_ROOT, d) for d in os.listdir(RECORDERS_ROOT)
                  if os.path.isdir(os.path.join(RECORDERS_ROOT, d))
                  and not d.startswith(('.', '_'))]
