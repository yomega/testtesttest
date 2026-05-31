from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Pdf3DProjectionType(Enum):
    """
    Specifies the available projection type of the 3D annotation.
    """

    Orthographic = 0
    Perspective = 1
