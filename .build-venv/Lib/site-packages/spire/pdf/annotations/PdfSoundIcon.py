from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfSoundIcon(Enum):
    """
    Specifies the name of an icon to be used in displaying the sound annotation.
    """

    Speaker = 0
    Mic = 1