from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class LoadHtmlType(Enum):
    """
    Enum class for loading HTML type.
    
    Attributes:
        URL (int): Load from URL.
        SourceCode (int): Load from source code.
    """
    URL = 0
    SourceCode = 1
