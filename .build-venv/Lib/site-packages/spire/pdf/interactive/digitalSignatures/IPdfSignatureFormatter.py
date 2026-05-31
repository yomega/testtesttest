from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class IPdfSignatureFormatter(abc.ABC):
    """
    Signature formatter.
    """

    @property
    @abc.abstractmethod
    def Properties(self) -> 'PdfSignatureProperties':
        """
        Signature properties.
        """

        pass


# @abc.abstractmethod
# def Sign(self, content: 'Byte[]') -> List['Byte']:
#     """
#     Sign.
#     Args: content: The data to be signed.
#     Returns: The signature.
#     """
#     pass