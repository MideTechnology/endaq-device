"""
Fake recorders for testing.
"""
import os.path

RECORDERS_ROOT = os.path.realpath(os.path.dirname(__file__))
RECORDER_PATHS = [os.path.join(RECORDERS_ROOT, d) for d in os.listdir(RECORDERS_ROOT)
                  if os.path.isdir(os.path.join(RECORDERS_ROOT, d))
                  and not d.startswith(('.', '_'))]

