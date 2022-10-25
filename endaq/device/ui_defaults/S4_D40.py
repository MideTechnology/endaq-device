"""
Default ConfigUI for S4-D40 data recorders 
"""

from base64 import b64decode

DEFAULT_CONFIG_UI = b64decode(
    b'd3dSw0AoRZNQBYdHZW5lcmFsQAXzUAWLRGV2aWNlIE5hbWVQAYMI/39RJIFAUBXYQSBjdX'
    b'N0b20gbmFtZSBmb3IgdGhlIHJlY29yZGVyLiBOb3QgdGhlIHNhbWUgYXMgdGhlIHZvbHVt'
    b'ZSBsYWJlbC4gNjQgY2hhcmFjdGVycyBtYXhpbXVtLkAF81AFjERldmljZSBOb3Rlc1ABgw'
    b'n/f1EkggEAUBXSQ3VzdG9tIG5vdGVzIGFib3V0IHRoZSByZWNvcmRlciAocG9zaXRpb24s'
    b'IHVzZXIgSUQsIGV0Yy4pLiAyNTYgY2hhcmFjdGVycyBtYXhpbXVtLlE0gQNABftQBZNSZW'
    b'NvcmRpbmcgRGlyZWN0b3J5UAGDFP9/UQSGUkVDT1JEUSSBEFAUk0NvbmZpZ1sweDE2RkY3'
    b'Rl09PTBQFblEaXJlY3RvcnkgZm9yIHNlcmlhbGl6ZWQgcmVjb3JkaW5ncy4gMTYgY2hhcm'
    b'FjdGVyIG1heGltdW1ABUCjUAWVUmVjb3JkaW5nIEZpbGUgUHJlZml4UAGDFf9/USSBEFAV'
    b'6FByZWZpeCBmb3Igc2VyaWFsaXplZCByZWNvcmRpbmcgbmFtZXMuIElmIGJsYW5rLCBkZX'
    b'ZpY2Ugc2VyaWFsIG51bWJlciB3aWxsIGJlIHVzZWQuIDE2IGNoYXJhY3RlciBtYXhpbXVt'
    b'UBSTQ29uZmlnWzB4MTZGRjdGXT09MEAHQTxQBY9GaWxlIE5hbWUgU3R5bGVQAYMW/39RAY'
    b'EBUBVA/FRpbWUtQmFzZWQgZmlsZSBuYW1lcyB1c2UgYSBkaXJlY3RvcnkgYmFzZWQgb24g'
    b'dGhlIGRhdGUsIGFuZCBmaWxlIG5hbWUgYmFzZWQgb24gdGhlIHNlY29uZHMgc2luY2UgbW'
    b'lkbmlnaHQuClNlcmlhbGl6ZWQgZmlsZSBuYW1lcyB1c2UgdGhlIHNwZWNpZmllZCBkaXJl'
    b'Y3RvcnkgYW5kIGZpbGUgbmFtZSBwcmVmaXgsIGZvbGxvd2VkIGJ5IGEgbnVtYmVyLiAKTn'
    b'VtYmVyIGlzIHJlc2V0IHdoZW4gZGlyZWN0b3J5IG9yIHByZWZpeCBjaGFuZ2VzLkEHjVAF'
    b'ilRpbWUgQmFzZWRBB41QBYpTZXJpYWxpemVkQAdAqVAFi0J1dHRvbiBNb2RlUAGDEP9/UQ'
    b'GBAFAVv09uZSBTZWNvbmQgUHJlc3Mgd2lsbCBkaXNhYmxlIDMtc2Vjb25kIHByZXNzIGZv'
    b'ciBiYXR0ZXJ5IGNoZWNrLkEHl1AFlEltbWVkaWF0ZSBTdGFydC9TdG9wQQeiUAWfT25lIF'
    b'NlY29uZCBQcmVzcyBmb3IgU3RhcnQvU3RvcEEHjVAFilN0YXJ0LU9ubHlAF0EUUAWOUGx1'
    b'Zy1JbiBBY3Rpb25QAYMK/39RAYEBUBWtU2V0IGFjdGlvbiBmb3IgZGV2aWNlIHdoZW4gcG'
    b'x1Z2dlZCBpbiB0byBVU0IuQQe1UAWySW1tZWRpYXRlbHkgc3RvcCByZWNvcmRpbmcgYW5k'
    b'IGFwcGVhciBhcyBVU0IgZHJpdmVBB7NQBbBDb21wbGV0ZSByZWNvcmRpbmcgYmVmb3JlIG'
    b'FwcGVhcmluZyBhcyBVU0IgZHJpdmVBB7BQBa1JZ25vcmU6IHN0b3AgcmVjb3JkaW5nIHdo'
    b'ZW4gYnV0dG9uIGlzIHByZXNzZWRBB6VQBaJTdGFydCByZWNvcmRpbmcgd2hlbiBVU0IgY2'
    b'9ubmVjdGVkQCPnUAGDC/9/UBXeRW50ZXIgbG9jYWwgdGltZXpvbmUncyBvZmZzZXQgZnJv'
    b'bSBVVEMgdGltZS4gSW1wYWN0cyB0aW1lc3RhbXAgaW5mb3JtYXRpb24gb24gcmVjb3JkaW'
    b'5nIGZpbGVzLkAvgEAPgEBPgEAoR3RQBYhUcmlnZ2Vyc0AHQNpQBYxUcmlnZ2VyIE1vZGVQ'
    b'AYMS/39RAYEAUBVAj0RlbGF5IFRoZW4gVHJpZ2dlcjogV2FpdCBzcGVjaWZpZWQgdGltZS'
    b'wgdGhlbiB3YWl0IGZvciB0cmlnZ2VyCkRlbGF5IE9yIFRyaWdnZXI6IEFjcXVpcmUgYWZ0'
    b'ZXIgd2FpdCBvciBvbiB0cmlnZ2VyLiBCYXR0ZXJ5IGxpZmUgbWF5IGJlIHJlZHVjZWQuQQ'
    b'eVUAWSRGVsYXkgVGhlbiBUcmlnZ2VyQQeTUAWQRGVsYXkgT3IgVHJpZ2dlckAy9FAFjVN0'
    b'YXJ0IGF0IFRpbWVQAYMP/39QFdtXYWl0IHVudGlsIHNldCB0aW1lIGJlZm9yZSBldmFsdW'
    b'F0aW5nIG90aGVyIHRyaWdnZXIgY29uZGl0aW9ucywgaW5jbHVkaW5nIGEgcmVjb3JkaW5n'
    b'IGRlbGF5QBGuUAWUUmVjb3JkaW5nIFRpbWUgTGltaXRQAYMN/39RIYT////wUCWHU2Vjb2'
    b'5kc0ARQJBQBZhSZWNvcmRpbmcgRGVsYXkvSW50ZXJ2YWxQAYMM/39RAYEAUCWHU2Vjb25k'
    b'c1EhgwFRgFAV2FRpbWUgYmVmb3JlIHN0YXJ0aW5nIGEgcmVjb3JkaW5nLCBhbmQgdGltZS'
    b'BiZXR3ZWVuIHJlY29yZGluZ3MgaWYgJ1JldHJpZ2dlcicgaXMgY2hlY2tlZC5AEa9QBZlS'
    b'ZWNvcmRpbmcgRmlsZSBTaXplIExpbWl0UAGDEf9/USGE////8FAlg0tpQkAQQJdQBYlSZX'
    b'RyaWdnZXJQAYMO/39QFLBDb25maWdbMHhERkY3Rl09PW51bGwgYW5kIENvbmZpZ1sweDEx'
    b'RkY3Rl09PW51bGxQFc9XaGVuIHNldCwgU2xhbSBTdGljayB3aWxsIHJlLWFybSBhZnRlci'
    b'ByZWNvcmRpbmcgdGltZSBvciBzaXplIGxpbWl0IGlzIHJlYWNoZWQuQBBAqFAFnldhaXQg'
    b'Zm9yIEFsbCBTZW5zb3IgQ29uZGl0aW9uc1ABgxP/f1AV/ldoZW4gc2V0LCByZWNvcmRpbm'
    b'cgd2lsbCBvbmx5IHN0YXJ0IHdoZW4gYWxsIHRyaWdnZXJzIGFyZSBtZXQsIG90aGVyd2lz'
    b'ZSByZWNvcmRpbmcgd2lsbCBzdGFydCB3aGVuIGFueSBzZW5zb3IgY29uZGl0aW9uIGlzIG'
    b'1ldEAYQQpQBZBQcmVzc3VyZSBUcmlnZ2VyUAGDBQAkUQCBAFAUmUNvbmZpZ1sweDAxRkYy'
    b'NF0gJiAxID09IDBAguVQBZVQcmVzc3VyZSBUcmlnZ2VyLCBMb3dQAYMDACRRAYMBX5BQJY'
    b'JQYVEhgwHUwFAVs1NldCB0byBzdGFydCBzYW1wbGluZyB3aGVuIG91dHNpZGUgcHJlc3N1'
    b'cmUgd2luZG93LkCC5lAFllByZXNzdXJlIFRyaWdnZXIsIEhpZ2hQAYMEACRRAYMBrbBQJY'
    b'JQYVEhgwHUwFAVs1NldCB0byBzdGFydCBzYW1wbGluZyB3aGVuIG91dHNpZGUgcHJlc3N1'
    b'cmUgd2luZG93LkAYQRdQBZNUZW1wZXJhdHVyZSBUcmlnZ2VyUAGDBQEkUQCBAFAUmUNvbm'
    b'ZpZ1sweDAxRkYyNF0gJiAyID09IDBAY+pQBZhUZW1wZXJhdHVyZSBUcmlnZ2VyLCBMb3dQ'
    b'AYMDASRRAoH2UCWBQ1ESgdhRIoFQUBW2U2V0IHRvIHN0YXJ0IHNhbXBsaW5nIHdoZW4gb3'
    b'V0c2lkZSB0ZW1wZXJhdHVyZSB3aW5kb3cuQGPrUAWZVGVtcGVyYXR1cmUgVHJpZ2dlciwg'
    b'SGlnaFABgwQBJFECgSNQJYFDURKB2FEigVBQFbZTZXQgdG8gc3RhcnQgc2FtcGxpbmcgd2'
    b'hlbiBvdXRzaWRlIHRlbXBlcmF0dXJlIHdpbmRvdy5AGEGjUAWaQWNjZWxlcmF0aW9uIFRy'
    b'aWdnZXIgKDQwZylQAYMH/1BQFdRMb3cgcG93ZXIgdHJpZ2dlciB1c2luZyBkaWdpdGFsIG'
    b'FjY2VsZXJvbWV0ZXIgd2l0aCBEQyByZXNwb25zZS4gTm8gcHJlLXRyaWdnZXIgZGF0YS5R'
    b'AIEAUBGDBf8IUBGDB/8gUCSAUBSUQ29uZmlnWzB4MWZmNTBdID09IDBAQ0CyUAWWQWNjZW'
    b'xlcmF0aW9uIFRocmVzaG9sZFABgwT/UFEBgiAAUgOIP0QAFAAUABRRI4hARAAAAAAAAFET'
    b'gFAV8kxvdyBwb3dlciB0cmlnZ2VyLiBUaGUgbWluaW11bSBhY2NlbGVyYXRpb24gKHBvc2'
    b'l0aXZlIG9yIG5lZ2F0aXZlKSB0byB0cmlnZ2VyIGEgcmVjb3JkaW5nLiBNdXN0IGJlIGdy'
    b'ZWF0ZXIgdGhhbiAwLkAnxlABgwX/UFEBgQdBB5FQBY5YIEF4aXMgVHJpZ2dlckEHkVAFjl'
    b'kgQXhpcyBUcmlnZ2VyQQeRUAWOWiBBeGlzIFRyaWdnZXJAD4BAT4BAKEWnUAWMTWVhc3Vy'
    b'ZW1lbnRzQAhBHFAFmzQwZyBEQyBBY2NlbGVyYXRpb24gKENoIDgwKUAnn1ABgwH/UFEBgQ'
    b'FBB5JQBY9FbmFibGUgQWxsIEF4ZXNAF0DYUAWLU2FtcGxlIFJhdGVQAYMC/1BRAYIB9FAl'
    b'gkh6UBXeTG93IHBhc3MgZmlsdGVyIGlzIHNldCB0byAyNSUgb2YgZGF0YSByYXRlLCBzby'
    b'BhIGRhdGEgcmF0ZSBvZiAyMDAwSHogaGFzIGEgTFAgZmlsdGVyIGF0IDUwMCBIelAUk25v'
    b'dCBDb25maWdbMHgxZmY1MF1BB4VRAYIPoEEHhVEBggfQQQeFUQGCA+hBB4VRAYIB9EEHhF'
    b'EBgfpBB4RRAYF9QQeEUQGBP0EHhFEBgSBBB4RRAYEQQAhBMFAFqENvbnRyb2wgUGFkIFRl'
    b'bXBlcmF0dXJlL1ByZXNzdXJlIChDaCA1OSlAJ0CbUQGBA1ABgwH/O1AVpUVuYWJsZS9EaX'
    b'NhYmxlIHNlbnNvcnMgb24gY29udHJvbCBwYWRBB5xQBZlFbmFibGUgUHJlc3N1cmUgKENo'
    b'IDU5LjApQQefUAWcRW5hYmxlIFRlbXBlcmF0dXJlIChDaCA1OS4xKUEHpVAFokVuYWJsZS'
    b'BSZWxhdGl2ZSBIdW1pZGl0eSAoQ2ggNTkuMilAEeNQBYtTYW1wbGUgUmF0ZVABgwL/O1AU'
    b'lENvbmZpZ1sweDFmZjNCXSA9PSAwUBWkU2V0IHNhbXBsZSBmcmVxdWVuY3kgZnJvbSAxIH'
    b'RvIDEwIEh6UQGBClAlgkh6URGBAVEhgQpACEHNUAWZSW5lcnRpYWwgTWVhc3VyZW1lbnQg'
    b'VW5pdEAHQJZQBZBBY3F1aXNpdGlvbiBNb2RlUAGDAf8rUCWBIFEBgRBBB4pQBYNPZmZRAY'
    b'EAQQeoUAWhQWJzb2x1dGUgT3JpZW50YXRpb24gKFF1YXRlcm5pb24pUQGBCEEHqFAFoVJl'
    b'bGF0aXZlIE9yaWVudGF0aW9uIChRdWF0ZXJuaW9uKVEBgRBBB49QBYhSb3RhdGlvblEBgQ'
    b'JAAUCGUAWVT3JpZW50YXRpb24gRGF0YSBSYXRlUAGDAggrUQGBZFAlgkh6URGBAVEhgchQ'
    b'Fb1TYW1wbGUgcmF0ZSBmb3IgZGlyZWN0aW9uYWwgZGF0YSBmcm9tIDEgdG8gMjAwIEh6Li'
    b'BDaGFubmVsIDY1UBSUQ29uZmlnWzB4MDFGRjJCXSA8IDhAAUCJUAWSUm90YXRpb24gRGF0'
    b'YSBSYXRlUAGDAgIrUQGBZFAlgkh6URGBAVEhgchQFb5TZXQgc2FtcGxlIHJhdGUgZm9yIH'
    b'JvdGF0aW9uIGRhdGEgZnJvbSAxIHRvIDIwMCBIei4gQ2hhbm5lbCA0N1AUmUNvbmZpZ1sw'
    b'eDAxRkYyQl0gJiAyID09IDBACEDxUAWlSW50ZXJuYWwgVGVtcGVyYXR1cmUvUHJlc3N1cm'
    b'UgKENoIDM2KUAnQMVRAYEDUAGDAf8kUBX3RW5hYmxlL0Rpc2FibGUgc2xvd2VyIGludGVy'
    b'bmFsIGVudmlyb25tZW50YWwgc2Vuc29ycy4gTk9URTogVGVtcGVyYXR1cmUgaXMgcmVxdW'
    b'lyZWQgZm9yIG1haW4gYWNjZWxlcm9tZXRlciBtZWFzdXJlbWVudHNBB5xQBZlFbmFibGUg'
    b'UHJlc3N1cmUgKENoIDM2LjApQQefUAWcRW5hYmxlIFRlbXBlcmF0dXJlIChDaCAzNi4xKU'
    b'AI9VAFoENvbnRyb2wgUGFkIExpZ2h0IFNlbnNvciAoQ2ggNzYpQCfPUAGDAf9MUBWjRW5h'
    b'YmxlL0Rpc2FibGUgbGlnaHQgc2Vuc29yIGF0IDQgSHpBB6BQBZ1FbmFibGUgTGlnaHQgU2'
    b'Vuc29yIChDaCA3Ni4wKUAPgEBPgEoIgEoogEpIgA=='
)