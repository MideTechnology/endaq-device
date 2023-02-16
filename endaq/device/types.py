"""
Type definitions, primarily for type hinting.
"""

from pathlib import Path
from typing import AnyStr, Optional, NamedTuple, Union


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


    def __str__(self):
        return str(self.path)


# ==============================================================================
# Type hinting definitions
# ==============================================================================

Epoch = Union[float, int]
Filename = Union[AnyStr, Path, Drive]


