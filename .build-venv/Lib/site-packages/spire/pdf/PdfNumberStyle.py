from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfNumberStyle(Enum):
    """
    Specifies numbering style of page labels.
    """
    none = 0
    Numeric = 1
    LowerLatin = 2
    LowerRoman = 3
    UpperLatin = 4
    UpperRoman = 5