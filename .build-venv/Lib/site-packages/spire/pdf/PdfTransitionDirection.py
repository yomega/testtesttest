from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfTransitionDirection(Enum):
    """
    Enumeration of transition directions.
    """
    LeftToRight = 0
    BottomToTop = 90
    RightToLeft = 180
    TopToBottom = 270
    TopLeftToBottomRight = 315