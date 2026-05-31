from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfAnnotationIntent(Enum):
    """
    Enum class for PDF annotation intents.
    """
    FreeTextCallout = 0
    FreeTextTypeWriter = 1
