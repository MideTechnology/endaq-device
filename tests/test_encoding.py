"""
Test basic HDLC encoding.
"""

from endaq.device import hdlc
import pytest

TEST_PAYLOADS = (
    b'~~ hello world! ~~',
    bytes(range(32)),
    bytes(range(128, 256))
)


@pytest.mark.parametrize("original", TEST_PAYLOADS)
def test_encode(original):
    """ Basic encoding/decoding tests w/o CRC. """
    encoded = hdlc.hdlc_encode(original, crc=False)
    assert encoded[-1] == hdlc.HDLC_BREAK
    assert hdlc.HDLC_BREAK not in encoded[:-1]  # ignore final break

    decoded = hdlc.hdlc_decode(encoded, ignore_crc=True)
    assert decoded.startswith(original)


@pytest.mark.parametrize("original", TEST_PAYLOADS)
def test_encode_crc(original):
    """ Basic encoding/decoding tests w/ CRC. """
    encoded = hdlc.hdlc_encode(original, crc=True)
    assert encoded[-1] == hdlc.HDLC_BREAK
    assert hdlc.HDLC_BREAK not in encoded[:-1]

    decoded = hdlc.hdlc_decode(encoded, ignore_crc=False)
    assert decoded.startswith(original)

    # encoded w/ CRC is 2 bytes longer than w/o
    no_crc = hdlc.hdlc_encode(original, crc=False)
    assert no_crc != encoded
    assert encoded.startswith(no_crc[:-1])
    assert len(no_crc) == len(encoded) - 2

    # Input w/ missing or bad CRC fails decoding
    with pytest.raises(hdlc.CRCError):
        _ = hdlc.hdlc_decode(no_crc, ignore_crc=False)


@pytest.mark.parametrize("original", TEST_PAYLOADS)
def test_encode_escapes(original):
    """ Encoding/decoding tests with additional escaped characters. """
    encoded = hdlc.hdlc_encode(original, crc=True, escaped=original)
    assert encoded[-1] == hdlc.HDLC_BREAK
    assert hdlc.HDLC_BREAK not in encoded[:-1]
    assert hdlc.HDLC_ESCAPE in encoded

    decoded = hdlc.hdlc_decode(encoded, ignore_crc=False)
    assert decoded.startswith(original)
