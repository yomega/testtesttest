from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfCheckBoxStyle(Enum):
    """
    Specifies the style for a check box field.
    
    The default value is Check.
    """
    Check = 0
    Circle = 1
    Cross = 2
    Diamond = 3
    Square = 4
    Star = 5