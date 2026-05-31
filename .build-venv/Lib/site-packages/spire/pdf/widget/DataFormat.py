from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class DataFormat(Enum):
    """
    Specifies the format of Export or Import data.
    """

    Xml = 0
    Fdf = 1
    XFdf = 2