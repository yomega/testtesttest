from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class LayerViewState(Enum):
    """
    Enum class that specifies the view state of the Layer.
    
    Attributes:
        Allways: The layer is always visible.
        Nerver: The layer is never visible.
        ViewWhenOpen: The layer is visible when the document is opened.
    """
    Allways = 0
    Nerver = 1
    ViewWhenOpen = 2