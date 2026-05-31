from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfLinearGradientMode(Enum):
    """
    Specifies the gradient direction of the linear gradient brush.
    """
    BackwardDiagonal = 0
    ForwardDiagonal = 1
    Horizontal = 2
    Vertical = 3