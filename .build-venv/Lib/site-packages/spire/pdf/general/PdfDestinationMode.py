from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfDestinationMode(Enum):
    """
    Enumeration that represents fit mode.
    """
    Location = 0
    FitToPage = 1
    FitH = 2
    FitR = 3
    FitBH = 4