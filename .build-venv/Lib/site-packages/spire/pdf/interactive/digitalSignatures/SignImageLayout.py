from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class SignImageLayout(Enum):
    """
    Enum class for determining the layout of the sign image.
    """

    none = 0
    Stretch = 1