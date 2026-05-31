from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfFillMode(Enum):
    """
    Specifies how the shapes are filled. 

    Attributes:
        Winding (int): Represents the winding fill mode.
        Alternate (int): Represents the alternate fill mode.
    """
    Winding = 0
    Alternate = 1