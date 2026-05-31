from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Pdf3DLightingStyle(Enum):
    """
    Specifies the available styles for applying light to 3D artwork. 
    """
    Artwork = 0
    none = 1
    White = 2
    Day = 3
    Night = 4
    Hard = 5
    Primary = 6
    Blue = 7
    Red = 8
    Cube = 9
    CAD = 10
    Headlamp = 11