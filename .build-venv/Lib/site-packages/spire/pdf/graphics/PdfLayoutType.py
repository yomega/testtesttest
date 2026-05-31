from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfLayoutType(Enum):
    """
    Enum class that specifies the type of paginating.
    """

    Paginate = 0
    OnePage = 1