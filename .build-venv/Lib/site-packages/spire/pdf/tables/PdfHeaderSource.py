from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfHeaderSource(Enum):
    """
    Specifies values specifying where the header should be formed from.
    """
    ColumnCaptions = 0
    Rows = 1