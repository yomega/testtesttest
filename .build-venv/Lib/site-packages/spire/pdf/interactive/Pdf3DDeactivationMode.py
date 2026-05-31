from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Pdf3DDeactivationMode(Enum):
    """
    Specifies the available modes for deactivating a 3D annotation. 
    """
    PageClose = 0
    PageInvisible = 1
    ExplicitDeactivation = 2