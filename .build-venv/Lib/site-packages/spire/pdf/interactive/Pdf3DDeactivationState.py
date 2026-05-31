from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Pdf3DDeactivationState(Enum):
    """
    Specifies the available states upon deactivating a 3D annotation. 
    """
    Uninstantiated = 0
    Instantiated = 1
    Live = 2
