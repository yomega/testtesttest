from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfBarcodeException(SpireObject):
    """
    Represents the general barcode exception class.
    """
    pass