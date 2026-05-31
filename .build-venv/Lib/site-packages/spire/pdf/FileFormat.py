from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class FileFormat(Enum):
    """
    Enum class that specifies the type of file format.
    """

    PDF = 0
    XPS = 1
    DOC = 2
    DOCX = 3
    HTML = 4
    SVG = 5
    PCL = 6
    XLSX = 7
    POSTSCRIPT = 8
    OFD = 9
    PPTX = 10
    Bin = 11
    Markdown = 12