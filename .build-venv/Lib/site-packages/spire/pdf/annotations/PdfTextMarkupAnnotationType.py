from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfTextMarkupAnnotationType(Enum):
    """
    Enum class that specifies the style of the Text Markup Annotation.
    
    Attributes:
        Highlight: Represents the highlight style.
        Underline: Represents the underline style.
        Squiggly: Represents the squiggly style.
        StrikeOut: Represents the strikeout style.
    """
    Highlight = 0
    Underline = 1
    Squiggly = 2
    StrikeOut = 3