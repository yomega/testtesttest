from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfActionDestination(Enum):
    """
    Specifies the available named actions supported by the viewer. 

    Attributes:
        FirstPage (int): Represents the first page action.
        LastPage (int): Represents the last page action.
        NextPage (int): Represents the next page action.
        PrevPage (int): Represents the previous page action.
    """
    FirstPage = 0
    LastPage = 1
    NextPage = 2
    PrevPage = 3