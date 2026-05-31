from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfSinglePageScalingMode(Enum):
    """
    Enum for Pdf Print Page Scale type.
    
    Attributes:
        FitSize: Scale the page to fit the size of the print area.
        ActualSize: Print the page at its actual size.
        ShrinkOversized: Shrink the page if it is larger than the print area.
        CustomScale: Scale the page to a custom scale specified by the user.
    """
    pass
    #FitSize = 0
    #ActualSize = 1
    #ShrinkOversized = 2
    #CustomScale = 3