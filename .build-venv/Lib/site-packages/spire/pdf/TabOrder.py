from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class TabOrder(Enum):
    """
    Enum class representing the tab order to be used for annotations on the page.
    
    Attributes:
        Row: Specifies tab order by row.
        Column: Specifies tab order by column.
        Structure: Specifies tab order by structure.
        Unspecified: Specifies an unspecified tab order.
    """
    Row = 0
    Column = 1
    Structure = 2
    Unspecified = 3