from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class CompressionLevel(Enum):
    """
    Enum class representing compression levels.

    Attributes:
        NoCompression: No compression.
        BestSpeed: Best speed compression.
        BelowNormal: Below normal compression.
        Normal: Normal compression.
        AboveNormal: Above normal compression.
        Best: Best compression.
    """
    NoCompression = 0
    BestSpeed = 1
    BelowNormal = 3
    Normal = 5
    AboveNormal = 7
    Best = 9