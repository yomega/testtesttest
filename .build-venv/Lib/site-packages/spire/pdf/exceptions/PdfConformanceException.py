from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfConformanceException(PdfDocumentException):
    """
    Exception of this type is raised when the document contains objects which are not supported by the current document standard.
    """
    pass