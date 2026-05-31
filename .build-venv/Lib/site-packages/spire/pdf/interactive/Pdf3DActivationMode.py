from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Pdf3DActivationMode(Enum):
    """
    Specifies the available modes for activating a 3D annotation. 

    Attributes:
        PageOpen: The 3D annotation is activated when the page is opened.
        PageVisible: The 3D annotation is activated when the page becomes visible.
        ExplicitActivation: The 3D annotation is activated explicitly.
    """
    PageOpen = 0
    PageVisible = 1
    ExplicitActivation = 2