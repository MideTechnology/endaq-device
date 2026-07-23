"""
Test various bits and bobs too small and random to merit their own scripts.
"""

import sys

import pytest
from endaq.device.exceptions import DeviceError
from endaq.device.response_codes import DeviceStatusCode


# ===========================================================================
# Exceptions
# ===========================================================================

@pytest.mark.parametrize('params,errno', [
    pytest.param((), None, id='no arguments'),
    pytest.param((-10,), DeviceStatusCode.ERR_BUSY, id='just int errno'),
    pytest.param((DeviceStatusCode.ERR_BUSY,), -10, id='just enum errno'),
    pytest.param((-10, None), -10, id='errno with null message'),
    pytest.param((-10, ''), -10, id='errno with empty message'),
    pytest.param((-10, 'message'), -10, id='errno with message'),
    pytest.param((-10, 'message', 'addendum', 42), -10, id='errno with message and extra args'),
    pytest.param((-999999,), -999999, id='unknown errno'),
    pytest.param((-999999, 'message'), -999999, id='unknown errno with message'),
    pytest.param((-999999, 'message', 'addendum', 42), -999999, id='unknown errno with extra args'),
    pytest.param(('message',), None, id='message without errno'),
])
def test_DeviceError_instantiation(params, errno):
    """ Basic variations of instantiation. Make sure `DeviceError`'s tricks
        work (converting integers to `DeviceStatusCode`/`CommandResponseCode`
        enum values, generating default messages, etc.)

        :param params: A tuple of init arguments.
        :param errno: The expected `errno` of the instantiated exception.
    """
    ex = DeviceError(*params)
    if len(params) > 0:
        assert ex.errno == errno
        if len(params) > 1:
            assert isinstance(ex.args[1], str)

    # Make sure the arguments end up in the exception's string.
    # NOTE: The way enums cast to strings changed in Python 3.11.
    #  Before 3.11, str(e) was the same as repr(e)
    #  In 3.11+, str(e) is the same as repr(e.value)
    if ex.args and isinstance(ex.args[0], DeviceStatusCode):
        if sys.hexversion > 0x3100000:
            assert all(str(arg) in str(ex) for arg in ex.args)
        else:
            assert repr(ex.args[0].value) in str(ex)
            assert all(str(arg) in str(ex) for arg in ex.args[1:])



def test_DeviceError_equivalents():
    """ Test exception contents with different arguments that should produce
        either equivalent or different values.
    """
    ex1 = DeviceError(-10)  # No message: use default
    ex2 = DeviceError(-10, None)  # Null message: use default
    ex3 = DeviceError(-10, '')  # Empty message: use default
    ex4 = DeviceError(-10, 'message')  # With message (don't use default)

    assert len(ex1.args) == 2
    assert len(ex2.args) == len(ex1.args)
    assert len(ex3.args) == len(ex2.args)
    assert len(ex4.args) == len(ex3.args)

    assert isinstance(ex1.args[1], str)
    assert isinstance(ex2.args[1], str)
    assert isinstance(ex3.args[1], str)
    assert isinstance(ex4.args[1], str)

    assert ex1.args == ex2.args
    assert ex2.args == ex3.args
    assert ex4.args != ex1.args
    assert ex4.args[1] != ex1.args[1]
    assert ex4.args[0] == ex1.args[0]
