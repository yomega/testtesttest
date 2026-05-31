from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfButtonIconScaleMode(Enum):
    """
    Represents the type of scaling to use.
    """
    Anamorphic = 0
    Proportional = 1