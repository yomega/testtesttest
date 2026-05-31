from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfStaticField(PdfAutomaticField):
    """
    Represents an automatic field whose value can be evaluated at the moment of creation.
    """
    pass