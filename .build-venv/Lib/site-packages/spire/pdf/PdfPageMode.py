from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfPageMode(Enum):
    """
    Enum representing the mode of document displaying.
    """
    UseNone = 0
    UseOutlines = 1
    UseThumbs = 2
    FullScreen = 3
    UseOC = 4
    UseAttachments = 5