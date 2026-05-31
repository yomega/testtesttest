from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfFontFamily(Enum):
    """
    Enum class representing the type of standard PDF fonts.

    Attributes:
        Helvetica: Represents the Helvetica font.
        Courier: Represents the Courier font.
        TimesRoman: Represents the Times Roman font.
        Symbol: Represents the Symbol font.
        ZapfDingbats: Represents the Zapf Dingbats font.
    """
    Helvetica = 0
    Courier = 1
    TimesRoman = 2
    Symbol = 3
    ZapfDingbats = 4