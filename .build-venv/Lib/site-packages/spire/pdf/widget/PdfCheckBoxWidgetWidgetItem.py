from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfCheckBoxWidgetWidgetItem(PdfStateWidgetItem):
    """
    Represents a loaded check box item.

    Attributes:
        PdfStateWidgetItem: The base class for the check box item.
    """
    pass