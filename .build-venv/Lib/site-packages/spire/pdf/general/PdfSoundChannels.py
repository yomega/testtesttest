from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfSoundChannels(Enum):
    """
    Enum class representing the number of sound channels.

    Attributes:
        Mono: Represents a mono sound channel.
        Stereo: Represents a stereo sound channel.
    """
    Mono = 1
    Stereo = 2