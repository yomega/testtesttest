from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Find_TextFindParameter(Enum):
    """
    Enum class for setting find text parameters.
    """
    none = 1
    WholeWord = 16
    IgnoreCase = 256
    CrossLine = 4096
    Regex = 65536