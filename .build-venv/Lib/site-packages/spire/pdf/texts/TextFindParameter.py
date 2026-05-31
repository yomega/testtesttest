from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class TextFindParameter(Enum):
    """
    Enum class for setting find text parameters.
    
    Attributes:
        none: No parameters set.
        WholeWord: Search for whole words only.
        IgnoreCase: Ignore case when searching.
        Regex: Use regular expressions for searching.
    """
    none = 1
    WholeWord = 16
    IgnoreCase = 256
    Regex = 65536