from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfHorizontalOverflowType(Enum):
    """
    Enum class representing the types of horizontal overflow in a PDF.
    
    Attributes:
        NextPage: Represents the next page as the overflow type.
        LastPage: Represents the last page as the overflow type.
    """
    NextPage = 0
    LastPage = 1