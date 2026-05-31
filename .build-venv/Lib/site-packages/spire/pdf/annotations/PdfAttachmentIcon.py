from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfAttachmentIcon(Enum):
    """
    Specifies the type of icon to be used in displaying file attachment annotations.
    """

    PushPin = 0
    Tag = 1
    Graph = 2
    Paperclip = 3