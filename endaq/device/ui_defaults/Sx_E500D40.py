"""
Default ConfigUI for S5-E500D40 data recorders 
"""

from base64 import b64decode

DEFAULT_CONFIG_UI = b64decode(
    b'd3dVh0AoRZNQBYdHZW5lcmFsQAXzUAWLRGV2aWNlIE5hbWVQAYMI/39RJIFAUBXYQSBjdX'
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
    b'5nIGZpbGVzLkAvgEAPgEBPgEAoSOhQBYhUcmlnZ2Vyc0AHQNpQBYxUcmlnZ2VyIE1vZGVQ'
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
    b'1ldEAYQO5QBZBQcmVzc3VyZSBUcmlnZ2VyUAGDBQAkUQCBAECC5VAFlVByZXNzdXJlIFRy'
    b'aWdnZXIsIExvd1ABgwMAJFEBgwFfkFAlglBhUSGDAdTAUBWzU2V0IHRvIHN0YXJ0IHNhbX'
    b'BsaW5nIHdoZW4gb3V0c2lkZSBwcmVzc3VyZSB3aW5kb3cuQILmUAWWUHJlc3N1cmUgVHJp'
    b'Z2dlciwgSGlnaFABgwQAJFEBgwGtsFAlglBhUSGDAdTAUBWzU2V0IHRvIHN0YXJ0IHNhbX'
    b'BsaW5nIHdoZW4gb3V0c2lkZSBwcmVzc3VyZSB3aW5kb3cuQBhA+1AFk1RlbXBlcmF0dXJl'
    b'IFRyaWdnZXJQAYMFASRRAIEAQGPqUAWYVGVtcGVyYXR1cmUgVHJpZ2dlciwgTG93UAGDAw'
    b'EkUQKB9lAlgUNREoHYUSKBUFAVtlNldCB0byBzdGFydCBzYW1wbGluZyB3aGVuIG91dHNp'
    b'ZGUgdGVtcGVyYXR1cmUgd2luZG93LkBj61AFmVRlbXBlcmF0dXJlIFRyaWdnZXIsIEhpZ2'
    b'hQAYMEASRRAoEjUCWBQ1ESgdhRIoFQUBW2U2V0IHRvIHN0YXJ0IHNhbXBsaW5nIHdoZW4g'
    b'b3V0c2lkZSB0ZW1wZXJhdHVyZSB3aW5kb3cuQBhBqFAFm0FjY2VsZXJhdGlvbiBUcmlnZ2'
    b'VyICg1MDBnKVABgwX/CFARgwf/IFEAgQBQJIBQFJVDb25maWdbMHgwMUZGMDhdID09IDBA'
    b'Q0CrUROIwH9AAAAAAABRI4hAf0AAAAAAAFAFmUFjY2VsZXJhdGlvbiBUcmlnZ2VyLCBMb3'
    b'dQAYMD/whRAoL5mlAV4EhpZ2ggcG93ZXIgdHJpZ2dlciB3aXRoIHByZS10cmlnZ2VyIGRh'
    b'dGEuIE5vdCByZWNvbW1lbmRlZCBmb3IgbG9uZyB3YWl0cyB3aXRob3V0IGV4dGVybmFsIH'
    b'Bvd2VyLlIDiD+PQB9AH0AfQENArFETiMB/QAAAAAAAUSOIQH9AAAAAAABQBZpBY2NlbGVy'
    b'YXRpb24gVHJpZ2dlciwgSGlnaFABgwT/CFECggZmUBXgSGlnaCBwb3dlciB0cmlnZ2VyIH'
    b'dpdGggcHJlLXRyaWdnZXIgZGF0YS4gTm90IHJlY29tbWVuZGVkIGZvciBsb25nIHdhaXRz'
    b'IHdpdGhvdXQgZXh0ZXJuYWwgcG93ZXIuUgOIP49AH0AfQB9AGEGjUAWaQWNjZWxlcmF0aW'
    b'9uIFRyaWdnZXIgKDQwZylQAYMH/1BQFdRMb3cgcG93ZXIgdHJpZ2dlciB1c2luZyBkaWdp'
    b'dGFsIGFjY2VsZXJvbWV0ZXIgd2l0aCBEQyByZXNwb25zZS4gTm8gcHJlLXRyaWdnZXIgZG'
    b'F0YS5RAIEAUBGDBf8IUBGDB/8gUCSAUBSUQ29uZmlnWzB4MWZmNTBdID09IDBAQ0CyUAWW'
    b'QWNjZWxlcmF0aW9uIFRocmVzaG9sZFABgwT/UFEBgiAAUgOIP0QAFAAUABRRI4hARAAAAA'
    b'AAAFETgFAV8kxvdyBwb3dlciB0cmlnZ2VyLiBUaGUgbWluaW11bSBhY2NlbGVyYXRpb24g'
    b'KHBvc2l0aXZlIG9yIG5lZ2F0aXZlKSB0byB0cmlnZ2VyIGEgcmVjb3JkaW5nLiBNdXN0IG'
    b'JlIGdyZWF0ZXIgdGhhbiAwLkAnxlABgwX/UFEBgQdBB5FQBY5YIEF4aXMgVHJpZ2dlckEH'
    b'kVAFjlkgQXhpcyBUcmlnZ2VyQQeRUAWOWiBBeGlzIFRyaWdnZXJAD4BAT4BAKEb3UAWMTW'
    b'Vhc3VyZW1lbnRzQAhCQVAFmDUwMGcgQWNjZWxlcmF0aW9uIChDaCA4KVAkgEAnQIFRAYEH'
    b'UAGDAf8IUBWgRW5hYmxlL0Rpc2FibGUgYWNjZWxlcmF0aW9uIGF4ZXNBB5lQBZZFbmFibG'
    b'UgWCBBeGlzIChDaCA4LjApQQeZUAWWRW5hYmxlIFkgQXhpcyAoQ2ggOC4xKUEHmVAFlkVu'
    b'YWJsZSBaIEF4aXMgKENoIDguMilAEUCaUAWLU2FtcGxlIFJhdGVQAYMC/whQFdhTZXQgbW'
    b'FpbiBhY2NlbGVyYXRpb24gc2FtcGxlIHJhdGUgZnJvbSAxMCB0byAyMDAwMCBIei4KSGln'
    b'aGVyIHJhdGUgcmVkdWNlcyBiYXR0ZXJ5IGxpZmUuUBSVQ29uZmlnWzB4MDFGRjA4XSA9PS'
    b'AwUQGCE4hQJYJIelERgQpRIYJOIEARQPxQBaNPdmVycmlkZSBBbnRpYWxpYXNpbmcgRmls'
    b'dGVyIEN1dG9mZlABgwj/CFEBggPoUCWCSHpRIYJhqFAVQKVEZWZhdWx0LCB3aGVuIG5vdC'
    b'BjaGVja2VkLCBvZiBvbmUtZmlmdGggc2FtcGxlIGZyZXF1ZW5jeS4gQ3V0LW9mZiBmcmVx'
    b'dWVuY3kgaGFzIDI5JSBhdHRlbnVhdGlvbi4KNXRoIG9yZGVyIEJ1dHRlcndvcnRoLiBTb2'
    b'1lIGF0dGVudWF0aW9uIGF0IDYwJSBvZiBjdXQtb2ZmIGZyZXF1ZW5jeS5QFJVDb25maWdb'
    b'MHgwMUZGMDhdID09IDBACEEcUAWbNDBnIERDIEFjY2VsZXJhdGlvbiAoQ2ggODApQCefUA'
    b'GDAf9QUQGBAUEHklAFj0VuYWJsZSBBbGwgQXhlc0AXQNhQBYtTYW1wbGUgUmF0ZVABgwL/'
    b'UFEBggH0UCWCSHpQFd5Mb3cgcGFzcyBmaWx0ZXIgaXMgc2V0IHRvIDI1JSBvZiBkYXRhIH'
    b'JhdGUsIHNvIGEgZGF0YSByYXRlIG9mIDIwMDBIeiBoYXMgYSBMUCBmaWx0ZXIgYXQgNTAw'
    b'IEh6UBSTbm90IENvbmZpZ1sweDFmZjUwXUEHhVEBgg+gQQeFUQGCB9BBB4VRAYID6EEHhV'
    b'EBggH0QQeEUQGB+kEHhFEBgX1BB4RRAYE/QQeEUQGBIEEHhFEBgRBACEEwUAWoQ29udHJv'
    b'bCBQYWQgVGVtcGVyYXR1cmUvUHJlc3N1cmUgKENoIDU5KUAnQJtRAYEDUAGDAf87UBWlRW'
    b'5hYmxlL0Rpc2FibGUgc2Vuc29ycyBvbiBjb250cm9sIHBhZEEHnFAFmUVuYWJsZSBQcmVz'
    b'c3VyZSAoQ2ggNTkuMClBB59QBZxFbmFibGUgVGVtcGVyYXR1cmUgKENoIDU5LjEpQQelUA'
    b'WiRW5hYmxlIFJlbGF0aXZlIEh1bWlkaXR5IChDaCA1OS4yKUAR41AFi1NhbXBsZSBSYXRl'
    b'UAGDAv87UBSUQ29uZmlnWzB4MWZmM0JdID09IDBQFaRTZXQgc2FtcGxlIGZyZXF1ZW5jeS'
    b'Bmcm9tIDEgdG8gMTAgSHpRAYEKUCWCSHpREYEBUSGBCkAIQc1QBZlJbmVydGlhbCBNZWFz'
    b'dXJlbWVudCBVbml0QAdAllAFkEFjcXVpc2l0aW9uIE1vZGVQAYMB/ytQJYEgUQGBEEEHil'
    b'AFg09mZlEBgQBBB6hQBaFBYnNvbHV0ZSBPcmllbnRhdGlvbiAoUXVhdGVybmlvbilRAYEI'
    b'QQeoUAWhUmVsYXRpdmUgT3JpZW50YXRpb24gKFF1YXRlcm5pb24pUQGBEEEHj1AFiFJvdG'
    b'F0aW9uUQGBAkABQIZQBZVPcmllbnRhdGlvbiBEYXRhIFJhdGVQAYMCCCtRAYFkUCWCSHpR'
    b'EYEBUSGByFAVvVNhbXBsZSByYXRlIGZvciBkaXJlY3Rpb25hbCBkYXRhIGZyb20gMSB0by'
    b'AyMDAgSHouIENoYW5uZWwgNjVQFJRDb25maWdbMHgwMUZGMkJdIDwgOEABQIlQBZJSb3Rh'
    b'dGlvbiBEYXRhIFJhdGVQAYMCAitRAYFkUCWCSHpREYEBUSGByFAVvlNldCBzYW1wbGUgcm'
    b'F0ZSBmb3Igcm90YXRpb24gZGF0YSBmcm9tIDEgdG8gMjAwIEh6LiBDaGFubmVsIDQ3UBSZ'
    b'Q29uZmlnWzB4MDFGRjJCXSAmIDIgPT0gMEAI9VAFoENvbnRyb2wgUGFkIExpZ2h0IFNlbn'
    b'NvciAoQ2ggNzYpQCfPUAGDAf9MUBWjRW5hYmxlL0Rpc2FibGUgbGlnaHQgc2Vuc29yIGF0'
    b'IDQgSHpBB6BQBZ1FbmFibGUgTGlnaHQgU2Vuc29yIChDaCA3Ni4wKUAPgEBPgEoIgEoogE'
    b'pIgA=='
)
