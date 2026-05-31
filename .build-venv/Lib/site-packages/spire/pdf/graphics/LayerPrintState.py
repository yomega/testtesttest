from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class LayerPrintState(Enum):
    """
    Enum class that specifies the print state of the Layer.
    
    Attributes:
        Allways: The layer should always be printed.
        Nerver: The layer should never be printed.
        PrintWhenVisible: The layer should be printed when it is visible.
    """
    Allways = 0
    Nerver = 1
    PrintWhenVisible = 2