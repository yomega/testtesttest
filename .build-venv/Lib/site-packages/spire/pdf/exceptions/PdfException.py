from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfException(SpireObject):
    """
    General exception class.
    """

    def __init__(self, message: str):
        """
        Initializes a new instance of the PdfException class.

        Args:
            message (str): The error message.
        """
        super().__init__(message)