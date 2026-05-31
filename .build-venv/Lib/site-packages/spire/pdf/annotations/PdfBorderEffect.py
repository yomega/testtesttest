from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfBorderEffect(Enum):
    """
    Enum class for different types of border effects in a PDF.
    """
    none = 0
    SmallCloud = 1
    BigCloud = 2