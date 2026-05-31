from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfCode128CBarcode(PdfUnidimensionalBarcode):
    """
    Represents a Code128C barcode.

    Only the following symbols are allowed in a Code 128C barcode: 0 1 2 3 4 5 6 7 8 9 FNC1 (\xF0). Code 128 C encodes only numeric symbols at double density, each pair of digits is encoded using a single symbol.
    """