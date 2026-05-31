from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfLineIntent(Enum):
    """
    Specifies the Line Intent Style to be used in the Line annotation.
    """
    LineArrow = 0
    LineDimension = 1