from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class AspectRatio(Enum):
    """
    Enumeration for aspect ratio options.
    """
    none = 0
    KeepWidth = 1
    KeepHeight = 2
    FitPageSize = 3
