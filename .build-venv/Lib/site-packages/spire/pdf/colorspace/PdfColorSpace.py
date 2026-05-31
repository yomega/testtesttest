from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfColorSpace(Enum):
    """
    Enum class that defines a set of color spaces.
    """

    RGB = 0
    CMYK = 1
    GrayScale = 2
    Indexed = 3