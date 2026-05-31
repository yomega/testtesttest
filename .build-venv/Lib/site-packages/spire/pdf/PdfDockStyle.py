from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfDockStyle(Enum):
    """
    Specifies the docking style of the page template.
    """
    none = 0
    Bottom = 1
    Top = 2
    Left = 3
    Right = 4
    Fill = 5