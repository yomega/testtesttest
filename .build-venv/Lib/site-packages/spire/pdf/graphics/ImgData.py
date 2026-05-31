from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class ImgData(abc.ABC):
    """
    Abstract base class for image data.
    """

    @property
    @abc.abstractmethod
    def TileWidth(self) -> int:
        """
        Returns the width of the tile.
        """
        pass

    @property
    @abc.abstractmethod
    def TileHeight(self) -> int:
        """
        Returns the height of the tile.
        """
        pass

    @property
    @abc.abstractmethod
    def NomTileWidth(self) -> int:
        """
        Returns the nominal width of the tile.
        """
        pass

    @property
    @abc.abstractmethod
    def NomTileHeight(self) -> int:
        """
        Returns the nominal height of the tile.
        """
        pass

    @property
    @abc.abstractmethod
    def ImgWidth(self) -> int:
        """
        Returns the width of the image.
        """
        pass

    @property
    @abc.abstractmethod
    def ImgHeight(self) -> int:
        """
        Returns the height of the image.
        """
        pass

    @property
    @abc.abstractmethod
    def NumComps(self) -> int:
        """
        Returns the number of components in the image.
        """
        pass

    @property
    @abc.abstractmethod
    def TileIdx(self) -> int:
        """
        Returns the index of the current tile.
        """
        pass

    @property
    @abc.abstractmethod
    def TilePartULX(self) -> int:
        """
        Returns the upper-left x-coordinate of the current tile part.
        """
        pass

    @property
    @abc.abstractmethod
    def TilePartULY(self) -> int:
        """
        Returns the upper-left y-coordinate of the current tile part.
        """
        pass

    @property
    @abc.abstractmethod
    def ImgULX(self) -> int:
        """
        Returns the upper-left x-coordinate of the image.
        """
        pass

    @property
    @abc.abstractmethod
    def ImgULY(self) -> int:
        """
        Returns the upper-left y-coordinate of the image.
        """
        pass

    @abc.abstractmethod
    def getCompSubsX(self, c: int) -> int:
        """
        Returns the horizontal subsampling factor for the specified component.
        """
        pass

    @abc.abstractmethod
    def getCompSubsY(self, c: int) -> int:
        """
        Returns the vertical subsampling factor for the specified component.
        """
        pass

    @abc.abstractmethod
    def getTileCompWidth(self, t: int, c: int) -> int:
        """
        Returns the width of the specified component in the specified tile.
        """
        pass

    @abc.abstractmethod
    def getTileCompHeight(self, t: int, c: int) -> int:
        """
        Returns the height of the specified component in the specified tile.
        """
        pass

    @abc.abstractmethod
    def getCompImgWidth(self, c: int) -> int:
        """
        Returns the width of the specified component in the image.
        """
        pass

    @abc.abstractmethod
    def getCompImgHeight(self, c: int) -> int:
        """
        Returns the height of the specified component in the image.
        """
        pass

    @abc.abstractmethod
    def getNomRangeBits(self, c: int) -> int:
        """
        Returns the number of bits in the nominal range for the specified component.
        """
        pass

    @abc.abstractmethod
    def setTile(self, x: int, y: int):
        """
        Sets the current tile to the tile at the specified coordinates.
        """
        pass

    @abc.abstractmethod
    def nextTile(self):
        """
        Moves to the next tile.
        """
        pass

    @abc.abstractmethod
    def getTile(self, co: 'Coord') -> 'Coord':
        """
        Returns the tile at the specified coordinates.
        """
        pass

    @abc.abstractmethod
    def getCompULX(self, c: int) -> int:
        """
        Returns the upper-left x-coordinate of the specified component.
        """
        pass

    @abc.abstractmethod
    def getCompULY(self, c: int) -> int:
        """
        Returns the upper-left y-coordinate of the specified component.
        """
        pass

    @dispatch
    @abc.abstractmethod
    def getNumTiles(self, co: Coord) -> Coord:
        """
        Returns the number of tiles in the specified coordinates.
        """
        pass

    @dispatch
    @abc.abstractmethod
    def getNumTiles(self) -> int:
        """
        Returns the total number of tiles.
        """
        pass