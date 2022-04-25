import os.path
import unittest

from endaq.device import EndaqS

S3_PATH = os.path.join(os.path.dirname(__file__), "fake_recorders", "S3-E25D40")


# @pytest.fixture(scope="session")
# def image_file(tmpdir_factory):
#     img = compute_expensive_image()
#     fn = tmpdir_factory.mktemp("data").join("img.png")
#     img.save(str(fn))
#     return fn


class BasicTestCase(unittest.TestCase):
    def setUp(self):
        self.device = EndaqS(S3_PATH, strict=False)


    def test_basics(self):
        self.assertEqual(self.device.productName, 'S3-E25D40')
        self.assertEqual(self.device.partNumber, 'S3-E25D40')


if __name__ == '__main__':
    unittest.main()
