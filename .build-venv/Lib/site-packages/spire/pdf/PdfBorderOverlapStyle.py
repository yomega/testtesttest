from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfBorderOverlapStyle(Enum):
    """
    Specifies values of the border overlap style.
    """
    Overlap = 0
    Inside = 1