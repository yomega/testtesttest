from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfLineCaptionType(Enum):
    """
    Enum class that specifies the Line Caption Type to be used in the Line annotation.
    
    Attributes:
        Inline: Represents the inline caption type.
        Top: Represents the top caption type.
    """
    Inline = 0
    Top = 1