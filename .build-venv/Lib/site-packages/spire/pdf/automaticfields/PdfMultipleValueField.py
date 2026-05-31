from enum import Enum
from plum import dispatch
from typing import TypeVar,Union,Generic,List,Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfMultipleValueField (  PdfDynamicField) :
    """
    Represents automatic field which has the same value within the 
    """
