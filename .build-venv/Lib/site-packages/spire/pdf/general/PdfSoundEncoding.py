from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfSoundEncoding(Enum):
    """
    Enum class representing the encoding format for the sample data.
    
    Attributes:
        Raw: The raw encoding format.
        Signed: The signed encoding format.
        MuLaw: The Mu-Law encoding format.
        ALaw: The A-Law encoding format.
    """
    Raw = 0
    Signed = 1
    MuLaw = 2
    ALaw = 3
