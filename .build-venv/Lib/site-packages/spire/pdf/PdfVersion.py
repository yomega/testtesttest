from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfVersion(Enum):
    """
    Specifies the available PDF versions to save a PDF document.
    """
    Version1_0 = 0
    Version1_1 = 1
    Version1_2 = 2
    Version1_3 = 3
    Version1_4 = 4
    Version1_5 = 5
    Version1_6 = 6
    Version1_7 = 7