from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfTextAnnotationIcon(Enum):
    """
    Specifies the enumeration of popup annotation icons.
    """
    Note = 0
    Comment = 1
    Help = 2
    Insert = 3
    Key = 4
    NewParagraph = 5
    Paragraph = 6