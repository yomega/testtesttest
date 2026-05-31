from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfCompressionLevel(Enum):
    """
    Enum class that defines data compression levels.
    """

    none = 0
    """
    No compression.
    """

    BestSpeed = 1
    """
    Compression level for best speed.
    """

    BelowNormal = 3
    """
    Compression level below normal.
    """

    Normal = 5
    """
    Normal compression level.
    """

    AboveNormal = 7
    """
    Compression level above normal.
    """

    Best = 9
    """
    Best compression level.
    """