from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class HttpReadType(Enum):
    """
    Specifies the different way of presenting the document at the client browser.
    """

    Open = 0
    Save = 1
