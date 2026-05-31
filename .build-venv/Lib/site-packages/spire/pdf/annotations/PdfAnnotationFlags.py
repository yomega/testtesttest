from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfAnnotationFlags(Enum):
    """
    Specifies the enumeration of the annotation flags.
    """
    Default = 0
    Invisible = 1
    Hidden = 2
    Print = 4
    NoZoom = 8
    NoRotate = 16
    NoView = 32
    ReadOnly = 64
    Locked = 128
    ToggleNoView = 256