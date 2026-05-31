from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class HttpMethod(Enum):
    """
    Specifies Http request method.
    """
    Get = 0
    Post = 1