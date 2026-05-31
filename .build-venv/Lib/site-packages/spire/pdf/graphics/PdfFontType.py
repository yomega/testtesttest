from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfFontType(Enum):
    """
    Enum class that specifies the type of the font.

    Attributes:
        Standard: Represents a standard font.
        TrueType: Represents a TrueType font.
        TrueTypeEmbedded: Represents an embedded TrueType font.
    """
    Standard = 0
    TrueType = 1
    TrueTypeEmbedded = 2