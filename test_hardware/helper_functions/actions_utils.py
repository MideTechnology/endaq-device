"""
Some basic helper functions to assist in utilizing Github Actions workflow commands.
https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions
"""
import os
import traceback as tb
from typing import List, Any, Literal

__all__ = ['debug', 'notice', 'warning', 'error', 'actions_exception', 'Group', 'print_test_name']


def getFileInfo():
    """
    Gets the line number and file name for the stack two levels above this one.
    """
    trace = tb.extract_stack()[-3]
    return trace.filename, trace.lineno


def debug(message: str):
    """
    Prints a message with the debug syntax from Github Actions Workflow Commands
    """
    print(f'\n::debug::{message}')


def _log(
    message: str, 
    sent_by: Literal["notice", "warning", "error"], 
    send_to: List[Any],
    file=None, 
    line=None, 
    endLine=None, 
    title=None,
    once_only=True):
    """
    creates a string with the syntax from Github Actions Workflow Commands
    This does not return anything, rather muting :param:`send_to` 
    """
    _file, _line = getFileInfo()

    output  = f'\n::{sent_by}'
    output += f' file={file or _file}'
    output += f',line={line or _line}'
    if endLine is not None: output += f',endLine={endLine}'
    if title is not None: output += f', title={title}'
    output += f'::{message}'

    if once_only and output in send_to:
        debug(message)
    else:
        send_to.append(output)
        print(output)
    
notices_sent = []
def notice(message: str, file=None, line=None, endLine=None, title=None, once_only: bool=True):
    """
    Prints a message with the notice syntax from Github Actions Workflow Commands
    """
    global notices_sent
    output = _log(message, "notice", notices_sent, file, line, endLine, title)


warnings_sent = []
def warning(message: str, file=None, line=None, endLine=None, title=None, once_only: bool=True):
    """
    Prints a message with the warning syntax from Github Actions Workflow Commands
    """
    global warnings_sent
    output = _log(message, "warning", file, line, endLine, title)

errors_sent = []
def error(message: str, file=None, line=None, endLine=None, title=None, once_only: bool=True):
    """
    Prints a message with the error syntax from Github Actions Workflow Commands
    """
    global errors_sent
    output = _log(message, "error", file, line, endLine, title)


def print_test_name(name: str):
    """
    For heavy duty debugging of tests, this will allow us to print out the test name for each test.
    Normally it should be just pass, but change to debug(name) for a whole bunch of text
    """
    pass

def actions_exception(e):
    """
    Prints a stack trace utilizing the github actions error syntax
    """
    trace = e.__traceback__
    frames = tb.extract_tb(trace)

    local_frames = [f for f in frames
                    if os.path.realpath(f.filename).startswith(os.path.abspath('..'))]

    error(
            '%0D%0A'.join(tb.format_exc().splitlines()),
            file=local_frames[-1].filename,
            line=local_frames[-1].lineno,
            title=e.__class__.__name__
            )
    exit(1)


class Group:
    """
    This will put any text output between its creation and destruction into a group for easy viewing
    Usage is:
    with Group('<Summary Text>'):
        <Lines to print in the group>
    """

    def __init__(self, name: str):
        self._name = name

    def __enter__(self):
        print(f'\n::group::{self._name}')

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('\n::endgroup::')
