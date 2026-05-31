from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class CustomFieldType(Enum):
    """
    Enum class representing custom field types.

    Attributes:
        TextField: Represents a text field.
        DateField: Represents a date field.
        NumberField: Represents a number field.
    """
    TextField = 0
    DateField = 1
    NumberField = 2