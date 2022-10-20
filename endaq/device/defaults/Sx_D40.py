"""
Default ConfigUI for S3-D40 data recorders 
"""

DEFAULT_CONFIG_UI = (
    b'd3dTfEAoRjBQBYdHZW5lcmFsQAXzUAWLRGV2aWNlIE5hbWVQAYMI/39RJIFAUBXYQSBjdX'
    b'N0b20gbmFtZSBmb3IgdGhlIHJlY29yZGVyLiBOb3QgdGhlIHNhbWUgYXMgdGhlIHZvbHVt'
    b'ZSBsYWJlbC4gNjQgY2hhcmFjdGVycyBtYXhpbXVtLkAF81AFjERldmljZSBOb3Rlc1ABgw'
    b'n/f1EkggEAUBXSQ3VzdG9tIG5vdGVzIGFib3V0IHRoZSByZWNvcmRlciAocG9zaXRpb24s'
    b'IHVzZXIgSUQsIGV0Yy4pLiAyNTYgY2hhcmFjdGVycyBtYXhpbXVtLlE0gQNABUCZUAWVQ3'
    b'VzdG9tIFJlY29yZGluZyBUYWdzUAGDF/9/UQSAUSSBQFAV8UtleXdvcmRzIGZvciBvcmdh'
    b'bml6aW5nIGFuZCBpZGVudGlmeWluZyByZWNvcmRpbmdzLCBzZXBhcmF0ZWQgYnkgY29tbW'
    b'Egb3Igc3BhY2UuIExpbWl0IGlzIDIwIHRhZ3MsIDY0IGNoYXJhY3RlcnMuQAX7UAWTUmVj'
    b'b3JkaW5nIERpcmVjdG9yeVABgxT/f1EEhlJFQ09SRFEkgRBQFJNDb25maWdbMHgxNkZGN0'
    b'ZdPT0wUBW5RGlyZWN0b3J5IGZvciBzZXJpYWxpemVkIHJlY29yZGluZ3MuIDE2IGNoYXJh'
    b'Y3RlciBtYXhpbXVtQAVAo1AFlVJlY29yZGluZyBGaWxlIFByZWZpeFABgxX/f1EkgRBQFe'
    b'hQcmVmaXggZm9yIHNlcmlhbGl6ZWQgcmVjb3JkaW5nIG5hbWVzLiBJZiBibGFuaywgZGV2'
    b'aWNlIHNlcmlhbCBudW1iZXIgd2lsbCBiZSB1c2VkLiAxNiBjaGFyYWN0ZXIgbWF4aW11bV'
    b'AUk0NvbmZpZ1sweDE2RkY3Rl09PTBAB0E8UAWPRmlsZSBOYW1lIFN0eWxlUAGDFv9/UQGB'
    b'AVAVQPxUaW1lLUJhc2VkIGZpbGUgbmFtZXMgdXNlIGEgZGlyZWN0b3J5IGJhc2VkIG9uIH'
    b'RoZSBkYXRlLCBhbmQgZmlsZSBuYW1lIGJhc2VkIG9uIHRoZSBzZWNvbmRzIHNpbmNlIG1p'
    b'ZG5pZ2h0LgpTZXJpYWxpemVkIGZpbGUgbmFtZXMgdXNlIHRoZSBzcGVjaWZpZWQgZGlyZW'
    b'N0b3J5IGFuZCBmaWxlIG5hbWUgcHJlZml4LCBmb2xsb3dlZCBieSBhIG51bWJlci4gCk51'
    b'bWJlciBpcyByZXNldCB3aGVuIGRpcmVjdG9yeSBvciBwcmVmaXggY2hhbmdlcy5BB41QBY'
    b'pUaW1lIEJhc2VkQQeNUAWKU2VyaWFsaXplZEAHQKlQBYtCdXR0b24gTW9kZVABgxD/f1EB'
    b'gQBQFb9PbmUgU2Vjb25kIFByZXNzIHdpbGwgZGlzYWJsZSAzLXNlY29uZCBwcmVzcyBmb3'
    b'IgYmF0dGVyeSBjaGVjay5BB5dQBZRJbW1lZGlhdGUgU3RhcnQvU3RvcEEHolAFn09uZSBT'
    b'ZWNvbmQgUHJlc3MgZm9yIFN0YXJ0L1N0b3BBB41QBYpTdGFydC1Pbmx5QBdBFFAFjlBsdW'
    b'ctSW4gQWN0aW9uUAGDCv9/UQGBAVAVrVNldCBhY3Rpb24gZm9yIGRldmljZSB3aGVuIHBs'
    b'dWdnZWQgaW4gdG8gVVNCLkEHtVAFskltbWVkaWF0ZWx5IHN0b3AgcmVjb3JkaW5nIGFuZC'
    b'BhcHBlYXIgYXMgVVNCIGRyaXZlQQezUAWwQ29tcGxldGUgcmVjb3JkaW5nIGJlZm9yZSBh'
    b'cHBlYXJpbmcgYXMgVVNCIGRyaXZlQQewUAWtSWdub3JlOiBzdG9wIHJlY29yZGluZyB3aG'
    b'VuIGJ1dHRvbiBpcyBwcmVzc2VkQQelUAWiU3RhcnQgcmVjb3JkaW5nIHdoZW4gVVNCIGNv'
    b'bm5lY3RlZEAj51ABgwv/f1AV3kVudGVyIGxvY2FsIHRpbWV6b25lJ3Mgb2Zmc2V0IGZyb2'
    b'0gVVRDIHRpbWUuIEltcGFjdHMgdGltZXN0YW1wIGluZm9ybWF0aW9uIG9uIHJlY29yZGlu'
    b'ZyBmaWxlcy5AL4BAD4BAT4BAKEd0UAWIVHJpZ2dlcnNAB0DaUAWMVHJpZ2dlciBNb2RlUA'
    b'GDEv9/UQGBAFAVQI9EZWxheSBUaGVuIFRyaWdnZXI6IFdhaXQgc3BlY2lmaWVkIHRpbWUs'
    b'IHRoZW4gd2FpdCBmb3IgdHJpZ2dlcgpEZWxheSBPciBUcmlnZ2VyOiBBY3F1aXJlIGFmdG'
    b'VyIHdhaXQgb3Igb24gdHJpZ2dlci4gQmF0dGVyeSBsaWZlIG1heSBiZSByZWR1Y2VkLkEH'
    b'lVAFkkRlbGF5IFRoZW4gVHJpZ2dlckEHk1AFkERlbGF5IE9yIFRyaWdnZXJAMvRQBY1TdG'
    b'FydCBhdCBUaW1lUAGDD/9/UBXbV2FpdCB1bnRpbCBzZXQgdGltZSBiZWZvcmUgZXZhbHVh'
    b'dGluZyBvdGhlciB0cmlnZ2VyIGNvbmRpdGlvbnMsIGluY2x1ZGluZyBhIHJlY29yZGluZy'
    b'BkZWxheUARrlAFlFJlY29yZGluZyBUaW1lIExpbWl0UAGDDf9/USGE////8FAlh1NlY29u'
    b'ZHNAEUCQUAWYUmVjb3JkaW5nIERlbGF5L0ludGVydmFsUAGDDP9/UQGBAFAlh1NlY29uZH'
    b'NRIYMBUYBQFdhUaW1lIGJlZm9yZSBzdGFydGluZyBhIHJlY29yZGluZywgYW5kIHRpbWUg'
    b'YmV0d2VlbiByZWNvcmRpbmdzIGlmICdSZXRyaWdnZXInIGlzIGNoZWNrZWQuQBGvUAWZUm'
    b'Vjb3JkaW5nIEZpbGUgU2l6ZSBMaW1pdFABgxH/f1EhhP////BQJYNLaUJAEECXUAWJUmV0'
    b'cmlnZ2VyUAGDDv9/UBSwQ29uZmlnWzB4REZGN0ZdPT1udWxsIGFuZCBDb25maWdbMHgxMU'
    b'ZGN0ZdPT1udWxsUBXPV2hlbiBzZXQsIFNsYW0gU3RpY2sgd2lsbCByZS1hcm0gYWZ0ZXIg'
    b'cmVjb3JkaW5nIHRpbWUgb3Igc2l6ZSBsaW1pdCBpcyByZWFjaGVkLkAQQKhQBZ5XYWl0IG'
    b'ZvciBBbGwgU2Vuc29yIENvbmRpdGlvbnNQAYMT/39QFf5XaGVuIHNldCwgcmVjb3JkaW5n'
    b'IHdpbGwgb25seSBzdGFydCB3aGVuIGFsbCB0cmlnZ2VycyBhcmUgbWV0LCBvdGhlcndpc2'
    b'UgcmVjb3JkaW5nIHdpbGwgc3RhcnQgd2hlbiBhbnkgc2Vuc29yIGNvbmRpdGlvbiBpcyBt'
    b'ZXRAGEEKUAWQUHJlc3N1cmUgVHJpZ2dlclABgwUAJFEAgQBQFJlDb25maWdbMHgwMUZGMj'
    b'RdICYgMSA9PSAwQILlUAWVUHJlc3N1cmUgVHJpZ2dlciwgTG93UAGDAwAkUQGDAV+QUCWC'
    b'UGFRIYMB1MBQFbNTZXQgdG8gc3RhcnQgc2FtcGxpbmcgd2hlbiBvdXRzaWRlIHByZXNzdX'
    b'JlIHdpbmRvdy5AguZQBZZQcmVzc3VyZSBUcmlnZ2VyLCBIaWdoUAGDBAAkUQGDAa2wUCWC'
    b'UGFRIYMB1MBQFbNTZXQgdG8gc3RhcnQgc2FtcGxpbmcgd2hlbiBvdXRzaWRlIHByZXNzdX'
    b'JlIHdpbmRvdy5AGEEXUAWTVGVtcGVyYXR1cmUgVHJpZ2dlclABgwUBJFEAgQBQFJlDb25m'
    b'aWdbMHgwMUZGMjRdICYgMiA9PSAwQGPqUAWYVGVtcGVyYXR1cmUgVHJpZ2dlciwgTG93UA'
    b'GDAwEkUQKB9lAlgUNREoHYUSKBUFAVtlNldCB0byBzdGFydCBzYW1wbGluZyB3aGVuIG91'
    b'dHNpZGUgdGVtcGVyYXR1cmUgd2luZG93LkBj61AFmVRlbXBlcmF0dXJlIFRyaWdnZXIsIE'
    b'hpZ2hQAYMEASRRAoEjUCWBQ1ESgdhRIoFQUBW2U2V0IHRvIHN0YXJ0IHNhbXBsaW5nIHdo'
    b'ZW4gb3V0c2lkZSB0ZW1wZXJhdHVyZSB3aW5kb3cuQBhBo1AFmkFjY2VsZXJhdGlvbiBUcm'
    b'lnZ2VyICg0MGcpUAGDB/9QUBXUTG93IHBvd2VyIHRyaWdnZXIgdXNpbmcgZGlnaXRhbCBh'
    b'Y2NlbGVyb21ldGVyIHdpdGggREMgcmVzcG9uc2UuIE5vIHByZS10cmlnZ2VyIGRhdGEuUQ'
    b'CBAFARgwX/CFARgwf/IFAkgFAUlENvbmZpZ1sweDFmZjUwXSA9PSAwQENAslAFlkFjY2Vs'
    b'ZXJhdGlvbiBUaHJlc2hvbGRQAYME/1BRAYIgAFIDiD9EABQAFAAUUSOIQEQAAAAAAABRE4'
    b'BQFfJMb3cgcG93ZXIgdHJpZ2dlci4gVGhlIG1pbmltdW0gYWNjZWxlcmF0aW9uIChwb3Np'
    b'dGl2ZSBvciBuZWdhdGl2ZSkgdG8gdHJpZ2dlciBhIHJlY29yZGluZy4gTXVzdCBiZSBncm'
    b'VhdGVyIHRoYW4gMC5AJ8ZQAYMF/1BRAYEHQQeRUAWOWCBBeGlzIFRyaWdnZXJBB5FQBY5Z'
    b'IEF4aXMgVHJpZ2dlckEHkVAFjlogQXhpcyBUcmlnZ2VyQA+AQE+AQChFw1AFjE1lYXN1cm'
    b'VtZW50c0AIQRxQBZs0MGcgREMgQWNjZWxlcmF0aW9uIChDaCA4MClAJ59QAYMB/1BRAYEB'
    b'QQeSUAWPRW5hYmxlIEFsbCBBeGVzQBdA2FAFi1NhbXBsZSBSYXRlUAGDAv9QUQGCAfRQJY'
    b'JIelAV3kxvdyBwYXNzIGZpbHRlciBpcyBzZXQgdG8gMjUlIG9mIGRhdGEgcmF0ZSwgc28g'
    b'YSBkYXRhIHJhdGUgb2YgMjAwMEh6IGhhcyBhIExQIGZpbHRlciBhdCA1MDAgSHpQFJNub3'
    b'QgQ29uZmlnWzB4MWZmNTBdQQeFUQGCD6BBB4VRAYIH0EEHhVEBggPoQQeFUQGCAfRBB4RR'
    b'AYH6QQeEUQGBfUEHhFEBgT9BB4RRAYEgQQeEUQGBEEAIQTBQBahDb250cm9sIFBhZCBUZW'
    b'1wZXJhdHVyZS9QcmVzc3VyZSAoQ2ggNTkpQCdAm1EBgQNQAYMB/ztQFaVFbmFibGUvRGlz'
    b'YWJsZSBzZW5zb3JzIG9uIGNvbnRyb2wgcGFkQQecUAWZRW5hYmxlIFByZXNzdXJlIChDaC'
    b'A1OS4wKUEHn1AFnEVuYWJsZSBUZW1wZXJhdHVyZSAoQ2ggNTkuMSlBB6VQBaJFbmFibGUg'
    b'UmVsYXRpdmUgSHVtaWRpdHkgKENoIDU5LjIpQBHjUAWLU2FtcGxlIFJhdGVQAYMC/ztQFJ'
    b'RDb25maWdbMHgxZmYzQl0gPT0gMFAVpFNldCBzYW1wbGUgZnJlcXVlbmN5IGZyb20gMSB0'
    b'byAxMCBIelEBgQpQJYJIelERgQFRIYEKQAhBzVAFmUluZXJ0aWFsIE1lYXN1cmVtZW50IF'
    b'VuaXRAB0CWUAWQQWNxdWlzaXRpb24gTW9kZVABgwH/K1AlgSBRAYEQQQeKUAWDT2ZmUQGB'
    b'AEEHqFAFoUFic29sdXRlIE9yaWVudGF0aW9uIChRdWF0ZXJuaW9uKVEBgQhBB6hQBaFSZW'
    b'xhdGl2ZSBPcmllbnRhdGlvbiAoUXVhdGVybmlvbilRAYEQQQePUAWIUm90YXRpb25RAYEC'
    b'QAFAhlAFlU9yaWVudGF0aW9uIERhdGEgUmF0ZVABgwIIK1EBgWRQJYJIelERgQFRIYHIUB'
    b'W9U2FtcGxlIHJhdGUgZm9yIGRpcmVjdGlvbmFsIGRhdGEgZnJvbSAxIHRvIDIwMCBIei4g'
    b'Q2hhbm5lbCA2NVAUlENvbmZpZ1sweDAxRkYyQl0gPCA4QAFAiVAFklJvdGF0aW9uIERhdG'
    b'EgUmF0ZVABgwICK1EBgWRQJYJIelERgQFRIYHIUBW+U2V0IHNhbXBsZSByYXRlIGZvciBy'
    b'b3RhdGlvbiBkYXRhIGZyb20gMSB0byAyMDAgSHouIENoYW5uZWwgNDdQFJlDb25maWdbMH'
    b'gwMUZGMkJdICYgMiA9PSAwQAhA8VAFpUludGVybmFsIFRlbXBlcmF0dXJlL1ByZXNzdXJl'
    b'IChDaCAzNilAJ0DFUQGBA1ABgwH/JFAV90VuYWJsZS9EaXNhYmxlIHNsb3dlciBpbnRlcm'
    b'5hbCBlbnZpcm9ubWVudGFsIHNlbnNvcnMuIE5PVEU6IFRlbXBlcmF0dXJlIGlzIHJlcXVp'
    b'cmVkIGZvciBtYWluIGFjY2VsZXJvbWV0ZXIgbWVhc3VyZW1lbnRzQQecUAWZRW5hYmxlIF'
    b'ByZXNzdXJlIChDaCAzNi4wKUEHn1AFnEVuYWJsZSBUZW1wZXJhdHVyZSAoQ2ggMzYuMSlA'
    b'CECQUAWgQ29udHJvbCBQYWQgTGlnaHQgU2Vuc29yIChDaCA3NilAJ+pQAYMB/0xQFb5Fbm'
    b'FibGUvRGlzYWJsZSBsaWdodCBzZW5zb3IgYXQgNCBIeiAtIE5PVEU6IERJU0FCTEVEIEZP'
    b'UiBBTFBIQUEHoFAFnUVuYWJsZSBMaWdodCBTZW5zb3IgKENoIDc2LjApQA+AQE+ASgiASi'
    b'iASkiA'
)
