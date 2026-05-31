from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfSubmitFormFlags(Enum):
    """
    Specifies the available data formats for submitting the form data.
    """
    IncludeExclude = 1
    IncludeNoValueFields = 2
    ExportFormat = 4
    GetMethod = 8
    SubmitCoordinates = 16
    Xfdf = 32
    IncludeAppendSaves = 64
    IncludeAnnotations = 128
    SubmitPdf = 256
    CanonicalFormat = 512
    ExclNonUserAnnots = 1024
    ExclFKey = 2048
    EmbedForm = 4096