from enum import Enum
from plum import dispatch
from typing import TypeVar,Union,Generic,List,Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfColorSpaces (SpireObject) :
    """
    Represents the base class for all colorspaces. 
    """
