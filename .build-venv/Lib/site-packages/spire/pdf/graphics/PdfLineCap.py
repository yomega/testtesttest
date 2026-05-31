from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfLineCap(Enum):
    """
    Specifies the line cap style to be used at the ends of the lines.
    """
    Flat = 0
    Round = 1
    Square = 2