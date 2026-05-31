from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfAnnotationException(PdfDocumentException):
    """
    Exception of this type is raised when annotation object is used incorrectly.
    """
    pass