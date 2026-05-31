from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfBorderStyle(Enum):
    """
    Specifies the available styles for a field border.
    """
    Solid = 0
    Dashed = 1
    Beveled = 2
    Inset = 3
    Underline = 4