from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfHighlightMode(Enum):
    """
    Specifies the highlight mode for a field.
    
    Default value is Invert.
    """
    NoHighlighting = 0
    Invert = 1
    Outline = 2
    Push = 3