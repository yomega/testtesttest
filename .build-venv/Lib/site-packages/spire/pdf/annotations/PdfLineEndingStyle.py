from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfLineEndingStyle(Enum):
    """
    Specifies the Line Ending Style to be used in the Line annotation.
    """
    Square = 0
    Circle = 1
    Diamond = 2
    OpenArrow = 3
    ClosedArrow = 4
    none = 5
    ROpenArrow = 6
    Butt = 7
    RClosedArrow = 8
    Slash = 9