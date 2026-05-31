from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfTextAlignment(Enum):
    """
    Specifies the type of horizontal text alignment.
    """
    Left = 0
    Center = 1
    Right = 2
    Justify = 3