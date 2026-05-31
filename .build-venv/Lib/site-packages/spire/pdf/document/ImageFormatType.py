from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class ImageFormatType(Enum):
    """
    Enum class for different image formats.
    """
    Original = 0
    Png = 1
    Jpeg = 2
    Bmp = 3