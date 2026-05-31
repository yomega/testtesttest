from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class IPdfTextBoxField(abc.ABC):
    """
    Interface for a PDF text box field.
    """

    @property
    @abc.abstractmethod
    def BackColor(self) -> 'PdfRGBColor':
        """
        Get or Set the background color of the field.

        Returns:
            A PdfRGBColor object specifying the background color of the field.
        """
        pass

    @BackColor.setter
    @abc.abstractmethod
    def BackColor(self, value: 'PdfRGBColor'):
        """
        Set the background color of the field.

        Args:
            value: A PdfRGBColor object specifying the background color of the field.
        """
        pass

    @property
    @abc.abstractmethod
    def ForeColor(self) -> 'PdfRGBColor':
        """
        Get or Set the fore color of the field.

        Returns:
            A PdfRGBColor object specifying the foreground color of the field.
        """
        pass

    @ForeColor.setter
    @abc.abstractmethod
    def ForeColor(self, value: 'PdfRGBColor'):
        """
        Set the fore color of the field.

        Args:
            value: A PdfRGBColor object specifying the foreground color of the field.
        """
        pass

    @property
    @abc.abstractmethod
    def TextAlignment(self) -> 'PdfTextAlignment':
        """
        Get or Set the text alignment in a text box.

        Returns:
            A PdfTextAlignment enumeration member specifying the text alignment in a text box.
        """
        pass

    @TextAlignment.setter
    @abc.abstractmethod
    def TextAlignment(self, value: 'PdfTextAlignment'):
        """
        Set the text alignment in a text box.

        Args:
            value: A PdfTextAlignment enumeration member specifying the text alignment in a text box.
        """
        pass

    @property
    @abc.abstractmethod
    def HighlightMode(self) -> 'PdfHighlightMode':
        """
        Get or Set the HighLightMode of the Field.

        Returns:
            A PdfHighlightMode enumeration member specifying the highlight mode in a text box.
        """
        pass

    @HighlightMode.setter
    @abc.abstractmethod
    def HighlightMode(self, value: 'PdfHighlightMode'):
        """
        Set the HighLightMode of the Field.

        Args:
            value: A PdfHighlightMode enumeration member specifying the highlight mode in a text box.
        """
        pass

    @property
    @abc.abstractmethod
    def Text(self) -> str:
        """
        Get or Set value of the text box field.

        Returns:
            A string value representing the value of the item.
        """
        pass

    @Text.setter
    @abc.abstractmethod
    def Text(self, value: str):
        """
        Set value of the text box field.

        Args:
            value: A string value representing the value of the item.
        """
        pass

    @property
    @abc.abstractmethod
    def DefaultValue(self) -> str:
        """
        Get or set the default value of the field.

        Returns:
            A string value representing the default value of the item.
        """
        pass

    @DefaultValue.setter
    @abc.abstractmethod
    def DefaultValue(self, value: str):
        """
        Set the default value of the field.

        Args:
            value: A string value representing the default value of the item.
        """
        pass

    @property
    @abc.abstractmethod
    def SpellCheck(self) -> bool:
        """
        Get or sets a value indicating whether to check spelling.

        Returns:
            True if the field content should be checked for spelling errors, false otherwise. Default is true.
        """
        pass

    @SpellCheck.setter
    @abc.abstractmethod
    def SpellCheck(self, value: bool):
        """
        Set a value indicating whether to check spelling.

        Args:
            value: True if the field content should be checked for spelling errors, false otherwise.
        """
        pass

    @property
    @abc.abstractmethod
    def InsertSpaces(self) -> bool:
        """
        Meaningful only if the MaxLength property is set and the Multiline, Password properties are false.
        If set, the field is automatically divided into as many equally spaced positions, or combs,
        as the value of MaxLength, and the text is laid out into those combs.
        """
        pass

    @InsertSpaces.setter
    @abc.abstractmethod
    def InsertSpaces(self, value: bool):
        """
        Set a value indicating whether to insert spaces.

        Args:
            value: True if the field should be divided into equally spaced positions, false otherwise.
        """
        pass

    @property
    @abc.abstractmethod
    def Multiline(self) -> bool:
        """
        Get or sets a value indicating whether this is multiline.

        Returns:
            True if the field is multiline, false otherwise. Default is false.
        """
        pass

    @Multiline.setter
    @abc.abstractmethod
    def Multiline(self, value: bool):
        """
        Set a value indicating whether this is multiline.

        Args:
            value: True if the field is multiline, false otherwise.
        """
        pass

    @property
    @abc.abstractmethod
    def Password(self) -> bool:
        """
        Get or sets a value indicating whether this is password field.

        Returns:
            True if the field is a password field, false otherwise. Default is false.
        """
        pass

    @Password.setter
    @abc.abstractmethod
    def Password(self, value: bool):
        """
        Set a value indicating whether this is password field.

        Args:
            value: True if the field is a password field, false otherwise.
        """
        pass

    @property
    @abc.abstractmethod
    def Scrollable(self) -> bool:
        """
        Get or sets a value indicating whether this is scrollable.

        Returns:
            True if the field content can be scrolled, false otherwise. Default is true.
        """
        pass

    @Scrollable.setter
    @abc.abstractmethod
    def Scrollable(self, value: bool):
        """
        Set a value indicating whether this is scrollable.

        Args:
            value: True if the field content can be scrolled, false otherwise.
        """
        pass

    @property
    @abc.abstractmethod
    def MaxLength(self) -> int:
        """
        Get or sets the maximum length of the field, in characters.

        Returns:
            A positive integer value specifying the maximum number of characters that can be entered in the text edit field.
        """
        pass

    @MaxLength.setter
    @abc.abstractmethod
    def MaxLength(self, value: int):
        """
        Set the maximum length of the field, in characters.

        Args:
            value: A positive integer value specifying the maximum number of characters that can be entered in the text edit field.
        """
        pass

    @property
    @abc.abstractmethod
    def Actions(self) -> 'PdfFieldActions':
        """
        Get the actions of the field.

        Returns:
            The actions.
        """
        pass

    @property
    @abc.abstractmethod
    def Bounds(self) -> 'RectangleF':
        """
        Get or sets the bounds.
        """
        pass

    @Bounds.setter
    @abc.abstractmethod
    def Bounds(self, value: 'RectangleF'):
        """
        Set the bounds.

        Args:
            value: The bounds of the field.
        """
       