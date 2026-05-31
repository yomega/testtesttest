from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class StoreType(Enum):
    """
    Enum class for specifying the naming of a system store.
    """

    MY = 0
    ROOT = 1
    CA = 2
    SPC = 3