import os.path
import unittest

from endaq.device import getRecorder

import fake_recorders

RECORDERS_ROOT = os.path.dirname(fake_recorders.__file__)
RECORDERS = [os.path.join(RECORDERS_ROOT, d) for d in os.listdir(RECORDERS_ROOT)
             if not d.startswith(('.', '_'))]
S3_PATH = os.path.join(os.path.dirname(__file__), "fake_recorders", "S3-E25D40")


# @pytest.fixture(scope="session")
# def image_file(tmpdir_factory):
#     img = compute_expensive_image()
#     fn = tmpdir_factory.mktemp("data").join("img.png")
#     img.save(str(fn))
#     return fn


class BasicTestCase(unittest.TestCase):
    # def setUp(self):
    #     self.device = EndaqS(S3_PATH, strict=False)


    def test_basics(self):
        for path in (p for p in RECORDERS if os.path.isdir(p)):
            dev = getRecorder(path, strict=False)
            self.assertEqual(dev.partNumber, os.path.basename(path))


if __name__ == '__main__':
    unittest.main()
