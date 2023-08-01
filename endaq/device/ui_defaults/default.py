"""
Default ConfigUI for unrecognized data recorders. It contains only the
UI items known to be universal (user-specified name, description,
and UTC offset widgets, and the calibration and info tabs.
"""

from base64 import b64decode

DEFAULT_CONFIG_UI = b64decode(
    b'GkXfoxAAAClChoEBQveBAULygQRC84EIQoKObWlkZS5zcy5jb25maWdCh4ECQoWBAnd3EA'
    b'ABk0AoEAABe1AFh0dlbmVyYWxABRAAAHNQBYtEZXZpY2UgTmFtZVABgwj/f1EkgUBQFdhB'
    b'IGN1c3RvbSBuYW1lIGZvciB0aGUgcmVjb3JkZXIuIE5vdCB0aGUgc2FtZSBhcyB0aGUgdm'
    b'9sdW1lIGxhYmVsLiA2NCBjaGFyYWN0ZXJzIG1heGltdW0uQAUQAABzUAWMRGV2aWNlIE5v'
    b'dGVzUAGDCf9/USSCAQBQFdJDdXN0b20gbm90ZXMgYWJvdXQgdGhlIHJlY29yZGVyIChwb3'
    b'NpdGlvbiwgdXNlciBJRCwgZXRjLikuIDI1NiBjaGFyYWN0ZXJzIG1heGltdW0uUTSBA0Aj'
    b'EAAAZ1ABgwv/f1AV3kVudGVyIGxvY2FsIHRpbWV6b25lJ3Mgb2Zmc2V0IGZyb20gVVRDIH'
    b'RpbWUuIEltcGFjdHMgdGltZXN0YW1wIGluZm9ybWF0aW9uIG9uIHJlY29yZGluZyBmaWxl'
    b'cy5ALxAAAABADxAAAABATxAAAABKCBAAAABKKBAAAABKSBAAAAA='
)
