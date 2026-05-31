from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class ImageQuality(Enum):
    """
    Enum class for ImageQuality.
    """
    High = 0
    Medium = 1
    Low = 2