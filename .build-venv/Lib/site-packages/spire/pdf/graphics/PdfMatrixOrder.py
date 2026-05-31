from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfMatrixOrder(Enum):
    """
    Enum class representing the applying order to matrix.
    
    Attributes:
        Prepend (int): Represents the prepend order.
        Append (int): Represents the append order.
    """
    Prepend = 0
    Append = 1