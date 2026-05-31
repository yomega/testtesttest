from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Security_SignImageLayout(Enum):
    """
    Enum class for determining the layout of the sign image.
    
    Attributes:
        none: No layout specified.
        stretch: Stretch the sign image to fit the designated area.
    """
    none = 0
    stretch = 1