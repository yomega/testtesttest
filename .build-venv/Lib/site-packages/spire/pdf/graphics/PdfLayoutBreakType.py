from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfLayoutBreakType(Enum):
    """
    Specifies how the element should be contained on the page.
    """
    FitPage = 0
    FitElement = 1
