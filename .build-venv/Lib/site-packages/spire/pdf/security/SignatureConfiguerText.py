from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class SignatureConfiguerText(Enum):
    """
    Enum class for configuring text options for a signature.
    
    Attributes:
        Name: The name of the signer.
        Location: The location of the signer.
        DistinguishedName: The distinguished name of the signer.
        Logo: The logo to be displayed.
        Date: The date of signing.
        Reason: The reason for signing.
        ContactInfo: The contact information of the signer.
        Labels: The labels to be displayed.
    """
    Name = 1
    Location = 2
    DistinguishedName = 4
    Logo = 8
    Date = 16
    Reason = 32
    ContactInfo = 64
    Labels = 128