from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Pdf3DActivationState(Enum):
    """
    Specifies an activation state of the 3D annotation.
    """
    Instantiated = 0
    Live = 1