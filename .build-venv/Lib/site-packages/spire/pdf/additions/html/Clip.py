from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Clip(Enum):
    """
    Options of converting html to pdf
    """
    none = 0
    Width = 1
    Height = 2
    Both = 4