import os.path
import unittest

from endaq.device import EndaqS
from endaq.device import config

S3_PATH = os.path.join(os.path.dirname(__file__), "fake_recorders", "S3-E25D40")


class BasicConfigTests(unittest.TestCase):
    def setUp(self):
        self.device = EndaqS(S3_PATH, strict=False)

    # def test_something(self):
    #     self.assertEqual(True, False)  # add assertion here


if __name__ == '__main__':
    unittest.main()
