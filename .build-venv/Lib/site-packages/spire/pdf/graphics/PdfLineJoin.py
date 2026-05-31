from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfLineJoin(Enum):
    """
    Enum class that specifies the corner style of the shapes.
    """

    Miter = 0
    Round = 1
    Bevel = 2