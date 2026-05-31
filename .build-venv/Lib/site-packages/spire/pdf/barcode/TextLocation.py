from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class TextLocation(Enum):
    """
    Specifies the barcode text display location.
    """
    none = 0
    Top = 1
    Bottom = 2