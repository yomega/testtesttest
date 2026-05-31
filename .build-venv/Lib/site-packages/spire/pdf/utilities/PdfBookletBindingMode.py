from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfBookletBindingMode(Enum):
    """
    Enum for Pdf print to booklet binding mode.
    
    Attributes:
        Left: Left binding mode.
        Right: Right binding mode.
    """
    Left = 0
    Right = 1