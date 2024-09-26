try:
    import paho
    import zeroconf
except ImportError as err:
    if 'paho' in err.msg or 'zeroconf' in err.msg:
        err.msg += ". Remote devices require the packages 'paho-mqtt' and 'zeroconf', not included in the base endaq.device install"
    raise
