from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfRubberStampAnnotationIcon(Enum):
    """
    Specifies the enumeration of rubber stamp annotation icons.
    """
    Additional = 0
    Approved = 1
    AsIs = 2
    Confidential = 3
    Departmental = 4
    Draft = 5
    Experimental = 6
    Expired = 7
    Final = 8
    ForComment = 9
    ForPublicRelease = 10
    NotApproved = 11
    NotForPublicRelease = 12
    Sold = 13
    TopSecret = 14