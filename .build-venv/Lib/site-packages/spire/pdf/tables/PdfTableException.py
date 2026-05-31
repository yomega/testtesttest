from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfTableException(PdfException):
    """
    Represents a message deliverer from the PdfTable class to the user.
    """
    pass