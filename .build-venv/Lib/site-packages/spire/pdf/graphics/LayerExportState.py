from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class LayerExportState(Enum):
    """
    Specifies the export state of the Layer
    """
    Allways = 0
    Nerver = 1
    ExportWhenVisible = 2