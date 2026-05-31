from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfTransitionStyle(Enum):
    """
    Enumeration of possible transition styles when moving to the page from another during a presentation.
    
    Attributes:
        Split: Split transition style.
        Blinds: Blinds transition style.
        Box: Box transition style.
        Wipe: Wipe transition style.
        Dissolve: Dissolve transition style.
        Glitter: Glitter transition style.
        Replace: Replace transition style.
        Fly: Fly transition style.
        Push: Push transition style.
        Cover: Cover transition style.
        Uncover: Uncover transition style.
        Fade: Fade transition style.
    """
    Split = 0
    Blinds = 1
    Box = 2
    Wipe = 3
    Dissolve = 4
    Glitter = 5
    Replace = 6
    Fly = 7
    Push = 8
    Cover = 9
    Uncover = 10
    Fade = 11