from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Security_GraphicMode(Enum):
    """
    Modes to determine what and how to display the signature information.
    """
    SignDetail = 0
    SignImageOnly = 1
    SignNameOnly = 2
    SignNameAndSignDetail = 3
    SignImageAndSignDetail = 4