from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfWordWrapType(Enum):
    """
    Specifies the types of text wrapping.
    """
    none = 0
    Word = 1
    WordOnly = 2
    Character = 3