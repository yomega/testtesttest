from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class Pdf3DRenderStyle(Enum):
    """
    Enum class that specifies the available rendering styles of the 3D artwork.
    
    Attributes:
        Solid: Represents a solid rendering style.
        SolidWireframe: Represents a solid wireframe rendering style.
        Transparent: Represents a transparent rendering style.
        TransparentWireframe: Represents a transparent wireframe rendering style.
        BoundingBox: Represents a bounding box rendering style.
        TransparentBoundingBox: Represents a transparent bounding box rendering style.
        TransparentBoundingBoxOutline: Represents a transparent bounding box outline rendering style.
        Wireframe: Represents a wireframe rendering style.
        ShadedWireframe: Represents a shaded wireframe rendering style.
        HiddenWireframe: Represents a hidden wireframe rendering style.
        Vertices: Represents a vertices rendering style.
        ShadedVertices: Represents a shaded vertices rendering style.
        Illustration: Represents an illustration rendering style.
        SolidOutline: Represents a solid outline rendering style.
        ShadedIllustration: Represents a shaded illustration rendering style.
    """
    Solid = 0
    SolidWireframe = 1
    Transparent = 2
    TransparentWireframe = 3
    BoundingBox = 4
    TransparentBoundingBox = 5
    TransparentBoundingBoxOutline = 6
    Wireframe = 7
    ShadedWireframe = 8
    HiddenWireframe = 9
    Vertices = 10
    ShadedVertices = 11
    Illustration = 12
    SolidOutline = 13
    ShadedIllustration = 14