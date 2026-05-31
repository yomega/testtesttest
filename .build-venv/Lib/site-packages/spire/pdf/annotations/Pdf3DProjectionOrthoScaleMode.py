from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Pdf3DProjectionOrthoScaleMode(Enum):
    """
    Specifies the available Ortho projection scaling mode of the 3D annotation.
    """

    Width = 0
    Height = 1
    Min = 2
    Max = 3
    Absolute = 4