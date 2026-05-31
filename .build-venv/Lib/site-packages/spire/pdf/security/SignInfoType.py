from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class SignInfoType(Enum):
    """
    Enum class representing different types of signatures.
    """

    SignInformation = 0
    """
    Represents sign information type.
    """

    DigitalSigner = 1
    """
    Represents digital signer type.
    """