from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class ReplaceActionType(Enum):
    """
    replace action Types
    
    Attributes:
        none: No action.
        WholeWord: Whole word. 
        IgnoreCase: Ignore English character case.
        AutofitWidth: Auto adjust word space.
        Regex: Regular expression matching.
    """
    none = 1
    WholeWord = 16
    IgnoreCase = 256
    AutofitWidth = 4096
    Regex = 65536