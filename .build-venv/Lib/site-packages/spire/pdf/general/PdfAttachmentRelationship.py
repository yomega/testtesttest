from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfAttachmentRelationship(Enum):
    """
    Enum class representing attachment relationship types.
    
    Attributes:
        Source: The attachment is the source of the document.
        Data: The attachment contains data related to the document.
        Alternative: The attachment is an alternative version of the document.
        Supplement: The attachment is a supplement to the document.
        Unspecified: The attachment relationship is unspecified.
    """
    Source = 0
    Data = 1
    Alternative = 2
    Supplement = 3
    Unspecified = 4