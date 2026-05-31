from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfStructContentItem(SpireObject):
    """
    Represents the pdf structure marked-content identifier or marked-content reference, object reference.
    """
    pass