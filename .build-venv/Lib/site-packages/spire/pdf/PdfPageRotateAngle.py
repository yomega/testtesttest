from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfPageRotateAngle(Enum):
    """
    Enum class representing the number of degrees by which the page should be rotated clockwise when displayed or printed.
    """
    RotateAngle0 = 0
    RotateAngle90 = 1
    RotateAngle180 = 2
    RotateAngle270 = 3