from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfHorizontalAlignment(Enum):
    """
    Enum class that specifies the type of Horizontal alignment.
    """

    Left = 0
    Center = 1
    Right = 2