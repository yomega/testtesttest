from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class FileRelatedFieldType(Enum):
    """
    Enum class for file related field types.

    Attributes:
        FileName: Represents the file name field.
        Desc: Represents the description field.
        ModDate: Represents the modification date field.
        CreationDate: Represents the creation date field.
        Size: Represents the size field.
    """
    FileName = 0
    Desc = 1
    ModDate = 2
    CreationDate = 3
    Size = 4