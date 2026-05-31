from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Pdf3DProjectionClipStyle(Enum):
    """
    Specifies the available clipping style of the 3D annotation.
    """

    ExplicitNearFar = 0
    AutomaticNearFar = 1