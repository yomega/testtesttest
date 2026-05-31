from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfEncryptionKeySize(Enum):
    """
    Enum class that specifies the length of the encryption key for encryption.
    
    Attributes:
        Key40Bit: 40-bit encryption key.
        Key128Bit: 128-bit encryption key.
        Key256Bit: 256-bit encryption key.
    """
    Key40Bit = 1
    Key128Bit = 2
    Key256Bit = 3