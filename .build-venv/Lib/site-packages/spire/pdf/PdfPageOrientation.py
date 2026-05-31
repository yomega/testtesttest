from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfPageOrientation(Enum):
    """
    Enumerator that implements page orientations.
    """

    Portrait = 0
    Landscape = 1