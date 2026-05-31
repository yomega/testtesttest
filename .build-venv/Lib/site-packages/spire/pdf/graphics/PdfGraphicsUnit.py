from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfGraphicsUnit(Enum):
    """
    Specifies the types of the page's logical units.
    """
    Centimeter = 0
    Pica = 1
    Pixel = 2
    Point = 3
    Inch = 4
    Document = 5
    Millimeter = 6