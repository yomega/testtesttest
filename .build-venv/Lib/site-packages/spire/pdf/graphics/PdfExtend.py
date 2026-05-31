from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfExtend(Enum):
    """
    Specifies the constant values specifying whether to extend the shading
    beyond the starting and ending points of the axis.
    """
    none = 0
    Start = 1
    End = 2
    Both = 3
