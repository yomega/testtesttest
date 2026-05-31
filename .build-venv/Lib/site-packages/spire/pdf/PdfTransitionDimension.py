from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfTransitionDimension(Enum):
    """
    Enumeration of transition dimensions.

    Attributes:
        Horizontal: Represents the horizontal dimension.
        Vertical: Represents the vertical dimension.
    """
    Horizontal = 0
    Vertical = 1