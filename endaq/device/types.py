"""
Type definitions, primarily for type hinting.
"""

from pathlib import Path
from typing import AnyStr, Optional, NamedTuple, TypeVar, Union


# ==============================================================================
# Data-containing classes
# ==============================================================================

class Drive(NamedTuple):
    """ Representation of basic drive/volume information. Used internally. """
    path: Union[AnyStr, Path]
    label: Optional[str]
    sn: Optional[str]
    label: Optional[str]
    fs: Optional[str]
    type: Optional[str]


# ==============================================================================
# Type hinting definitions
# ==============================================================================

Epoch = TypeVar('Epoch', float, int)
Filename = TypeVar('Filename', AnyStr, Path, Drive)


