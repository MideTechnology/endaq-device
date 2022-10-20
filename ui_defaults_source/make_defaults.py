"""
Some functions to help generate default ConfigUI data modules from 'canned'
data taken from actual device `CONFIG.UI` files. For internal development
work.

It is expected that the name of each source file matches the part
number of the device from which it was taken, plus the extension ".UI".

TODO: Handle HwRev/BOM variants? This would really just be a change in the
  naming conventions here; the work would be in `endaq.device.ui_defaults`.
TODO: Make a utility? This is currently used directly from the REPR.
TODO: Process .UI files to remove unnecessary elements? It would save
  a couple hundred bytes, but not much more.
"""

import base64
from collections import defaultdict
import os


# Source of unconverted .UI files
root = os.path.dirname(__file__)

# Path for Python modules
defaults = os.path.abspath(os.path.join(root, '../endaq/device/ui_defaults'))


def getGenericName(pn: str) -> str:
    """ Create a 'generic' version of a product part number.
    """
    if pn.startswith('LOG-'):
        return pn
    family, sep, model = pn.partition('-')
    return "{}x{}{}".format(family[0], sep, model)


def getDupes(path=root):
    """ Collect all .UI files and generate a dictionary mapping the
        name of each corresponding Python module to its source.
        Generic module names are used if any .UI files are identical.

        :param path: The directory containing the .UI files.
        :return: A dictionary of module names mapped to source .UI names.
    """
    hashes = defaultdict(list)

    for fn in os.listdir(path):
        if not fn.endswith('.UI'):
            continue
        with open(os.path.join(path, fn), 'rb') as f:
            data = f.read()
        hashes[hash(data)].append(fn)

    result = {}
    for names in hashes.values():
        name = os.path.splitext(os.path.basename(names[0]))[0]
        if len(names) < 2:
            result[name] = name
        else:
            for n in names:
                if n.startswith('LOG-'):
                    name = mname = os.path.splitext(n)[0]
                else:
                    mname = getGenericName(name)
                    name = os.path.splitext(os.path.basename(n))[0]
                result[mname.replace('-', '_')] = name

    return result


def wrap(t, w):
    """ Simple line-wrapper (textwrap.wrap in py39 didn't like some of the data).
    """
    return [t[i:i+w] for i in range(0, len(t), w)]


def makeModule(pn, pyname=None, inpath=root, outpath=defaults):
    """ Create a Python module from a .UI file. Input and output names should
        not have path or file extensions.

        :param pn: The name of the source .UI file.
        :param pyname: The output name of the Python module.
        :param inpath: The directory containing the .UI files.
        :param outpath: The directory into which to write the .py files.
    """
    pyname = (pyname or pn).replace('-', '_')
    with open(os.path.join(inpath, pn + ".UI"), 'rb') as f:
        data = f.read()
    with open(os.path.join(outpath, pyname + ".py"), 'w') as f:
        f.write(f'"""\nDefault ConfigUI for {pn} data recorders \n"""'
                '\n\n'
                'DEFAULT_CONFIG_UI = (\n')
        for line in wrap(base64.b64encode(data), 70):
            f.write(f"    {line!r}\n")
        f.write(')\n')


def makeModules(inpath=root, outpath=defaults):
    """ Create all Python modules for all .UI files. If two or more
        .UI files are identical, a single 'generic' module is made.

        :param inpath: The directory containing the .UI files.
        :param outpath: The directory into which to write the .py files.
    """
    for pyname, pn in getDupes(inpath).items():
        print(f'Creating module {pyname!r} from source {pn!r}')
        makeModule(pn, pyname, inpath=inpath, outpath=outpath)
