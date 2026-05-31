from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class SimpleTextExtractionStrategy(SpireObject):
    """
    This extractor keeps track of the current Y position of each string. 
    If it detects that the y position has changed, it inserts a line break into the output.
    If the PDF extractor text in a non-top-to-bottom fashion, this will result in the text not being a true representation of how it appears in the PDF.
    
    Returns:
        The Extracted Text.
    """