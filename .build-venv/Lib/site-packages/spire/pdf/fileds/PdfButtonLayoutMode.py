from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfButtonLayoutMode(Enum):
    """
    Enum representing the button layout mode.
    
    Attributes:
        CaptionOnly: Button with caption only.
        IconOnly: Button with icon only.
        CaptionBelowIcon: Button with caption below icon.
        CaptionAboveIcon: Button with caption above icon.
        CaptionRightOfIcon: Button with caption right of icon.
        CaptionLeftOfIcon: Button with caption left of icon.
        CaptionOverlayIcon: Button with caption overlay icon.
    """
    CaptionOnly = 0
    IconOnly = 1
    CaptionBelowIcon = 2
    CaptionAboveIcon = 3
    CaptionRightOfIcon = 4
    CaptionLeftOfIcon = 5
    CaptionOverlayIcon = 6