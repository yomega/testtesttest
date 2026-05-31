from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfFontStyle(Enum):
    """
    Specifies style information applied to text.
    """
    Regular = 0
    Bold = 1
    Italic = 2
    Underline = 4
    Strikeout = 8