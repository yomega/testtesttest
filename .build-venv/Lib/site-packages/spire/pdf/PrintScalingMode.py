from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PrintScalingMode(Enum):
    """
    Specifies the different page scaling option that shall be selected when a print dialog is displayed for this document.
    
    Default value is AppDefault.
    """
    AppDefault = 0
    none = 1