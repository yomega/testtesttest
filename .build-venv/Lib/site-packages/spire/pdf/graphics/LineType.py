from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class LineType(Enum):
    """
    Enum representing the break type of a line.
    """
    none = 0
    NewLineBreak = 1
    LayoutBreak = 2
    FirstParagraphLine = 4
    LastParagraphLine = 8
