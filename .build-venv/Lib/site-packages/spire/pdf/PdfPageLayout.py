from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfPageLayout(Enum):
    """
    Enum class representing different page layouts for a PDF document.

    Attributes:
        SinglePage: A single page layout.
        OneColumn: A one column layout.
        TwoColumnLeft: A two column layout with the first column on the left.
        TwoColumnRight: A two column layout with the first column on the right.
        TwoPageLeft: A two page layout with the first page on the left.
        TwoPageRight: A two page layout with the first page on the right.
    """
    SinglePage = 0
    OneColumn = 1
    TwoColumnLeft = 2
    TwoColumnRight = 3
    TwoPageLeft = 4
    TwoPageRight = 5