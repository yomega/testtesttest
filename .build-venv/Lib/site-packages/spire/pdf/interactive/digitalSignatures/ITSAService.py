from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class ITSAService(abc.ABC):
    """
    Timestamp provider interface.
    """

    @abc.abstractmethod
    def Generate(self, signature: 'Byte[]') -> List['Byte']:
        """
        Generate timestamp token.

        Args:
            signature: The value of signature field within SignerInfo.
                       The value of messageImprint field within TimeStampToken shall be the hash of signature.
                       Refrence RFC 3161 APPENDIX A.

        Returns:
            timestamp which must conform to RFC 3161
        """
        pass