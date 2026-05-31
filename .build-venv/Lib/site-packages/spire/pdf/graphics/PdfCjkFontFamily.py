from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfCjkFontFamily(Enum):
    """
    Specifies the type of CJK font.
    """
    HanyangSystemsGothicMedium = 2
    HanyangSystemsShinMyeongJoMedium = 3
    HeiseiKakuGothicW5 = 0
    HeiseiMinchoW3 = 1
    MonotypeHeiMedium = 4
    MonotypeSungLight = 5
    SinoTypeSongLight = 6