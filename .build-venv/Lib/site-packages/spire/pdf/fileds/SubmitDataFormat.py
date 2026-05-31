from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class SubmitDataFormat(Enum):
    """
    Specifies the enumeration of submit data formats.
    """
    Html = 0
    Pdf = 1
    Fdf = 2
    Xfdf = 3