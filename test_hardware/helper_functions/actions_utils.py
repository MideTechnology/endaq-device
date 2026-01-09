"""
Some basic helper functions to assist in utilizing Github Actions workflow commands.
https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions
"""
import os
import traceback as tb

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

notices_sent = []
def notice(message: str, file=None, line=None, endLine=None, title=None, once_only: bool=True):
    """
    Prints a message with the notice syntax from Github Actions Workflow Commands
    """
    global notices_sent
    _file, _line = getFileInfo()

    output = '\n::notice'

    if file is None:
        output += f' file={_file}'
    else:
        output += f' file={file}'

    if line is None:
        output += f',line={_line}'
    else:
        output += f',line={line}'

    if endLine is not None:
        output += f',endLine={endLine}'

    if title is not None:
        output += f',title={title}'

    output += f'::{message}'

    if once_only and output in notices_sent:
        debug(message)
    else:
        notices_sent.append(output)
        print(output)

warnings_sent = []
def warning(message: str, file=None, line=None, endLine=None, title=None, once_only: bool=True):
    """
    Prints a message with the warning syntax from Github Actions Workflow Commands
    """
    global warnings_sent
    _file, _line = getFileInfo()

    output = '\n::warning'

    if file is None:
        output += f' file={_file}'
    else:
        output += f' file={file}'

    if line is None:
        output += f',line={_line}'
    else:
        output += f',line={line}'

    if endLine is not None:
        output += f',endLine={endLine}'

    if title is not None:
        output += f',title={title}'

    output += f'::{message}'


    if once_only and output in warnings_sent:
        debug(message)
    else:
        warnings_sent.append(output)
        print(output)


errors_sent = []
def error(message: str, file=None, line=None, endLine=None, title=None, once_only: bool=True):
    """
    Prints a message with the error syntax from Github Actions Workflow Commands
    """
    _file, _line = getFileInfo()

    output = '\n::error'

    if file is None:
        output += f' file={_file}'
    else:
        output += f' file={file}'

    if line is None:
        output += f',line={_line}'
    else:
        output += f',line={line}'

    if endLine is not None:
        output += f',endLine={endLine}'

    if title is not None:
        output += f',title={title}'

    output += f'::{message}'

    if once_only and output in errors_sent:
        debug(message)
    else:
        errors_sent.append(output)
        print(output)

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
