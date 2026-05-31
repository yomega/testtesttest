from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfUnorderedMarkerStyle(Enum):
    """
    Enum class for specifying the marker style.
    """

    none = 0
    Disk = 1
    Square = 2
    Asterisk = 3
    Circle = 4
    CustomString = 5
    CustomImage = 6
    CustomTemplate = 7