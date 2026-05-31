from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class TextAlign(Enum):
    """
    Specifies how text in a PDF is horizontally aligned.
    
    Attributes:
        Left: Aligns the text to the left.
        Right: Aligns the text to the right.
        Center: Centers the text.
        Justify: Justifies the text.
    """
    Left = 1
    Right = 2
    Center = 3
    Justify = 4