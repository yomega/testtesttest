from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class IPdfComboBoxField(abc.ABC):
    """
    Interface for PDF combo box fields.
    """

    @property
    @abc.abstractmethod
    def Editable(self) -> bool:
        """
        Gets or sets a value indicating whether this field is editable.
        """
        pass

    @Editable.setter
    @abc.abstractmethod
    def Editable(self, value: bool):
        """
        Sets the value indicating whether this field is editable.
        """
        pass

    @property
    @abc.abstractmethod
    def SelectedIndex(self) -> int:
        """
        Gets or sets the index of the first selected item in the list.
        """
        pass

    @SelectedIndex.setter
    @abc.abstractmethod
    def SelectedIndex(self, value: int):
        """
        Sets the index of the first selected item in the list.
        """
        pass

    @property
    @abc.abstractmethod
    def SelectedValue(self) -> str:
        """
        Gets or sets the value of the first selected item in the list.
        """
        pass

    @SelectedValue.setter
    @abc.abstractmethod
    def SelectedValue(self, value: str):
        """
        Sets the value of the first selected item in the list.
        """
        pass

    @property
    @abc.abstractmethod
    def SelectedItem(self) -> 'PdfListFieldItem':
        """
        Gets the first selected item in the list.
        """
        pass

    @property
    @abc.abstractmethod
    def Bounds(self) -> 'RectangleF':
        """
        Gets or sets the bounds.
        """
        pass

    @Bounds.setter
    @abc.abstractmethod
    def Bounds(self, value: 'RectangleF'):
        """
        Sets the bounds.
        """
        pass

    @property
    @abc.abstractmethod
    def Location(self) -> 'PointF':
        """
        Gets or sets the location.
        """
        pass

    @Location.setter
    @abc.abstractmethod
    def Location(self, value: 'PointF'):
        """
        Sets the location.
        """
        pass

    @property
    @abc.abstractmethod
    def Size(self) -> 'SizeF':
        """
        Gets or sets the size.
        """
        pass

    @Size.setter
    @abc.abstractmethod
    def Size(self, value: 'SizeF'):
        """
        Sets the size.
        """
        pass

    @property
    @abc.abstractmethod
    def BorderColor(self) -> 'PdfRGBColor':
        """
        Gets or sets the color of the border.
        """
        pass

    @BorderColor.setter
    @abc.abstractmethod
    def BorderColor(self, value: 'PdfRGBColor'):
        """
        Sets the color of the border.
        """
        pass

    @property
    @abc.abstractmethod
    def BackColor(self) -> 'PdfRGBColor':
        """
        Gets or sets the color of the background.
        """
        pass

    @BackColor.setter
    @abc.abstractmethod
    def BackColor(self, value: 'PdfRGBColor'):
        """
        Sets the color of the background.
        """
        pass

    @property
    @abc.abstractmethod
    def ForeColor(self) -> 'PdfRGBColor':
        """
        Gets or sets the color of the text.
        """
        pass

    @ForeColor.setter
    @abc.abstractmethod
    def ForeColor(self, value: 'PdfRGBColor'):
        """
        Sets the color of the text.
        """
        pass

    @property
    @abc.abstractmethod
    def BorderWidth(self) -> float:
        """
        Gets or sets the width of the border.
        """
        pass

    @BorderWidth.setter
    @abc.abstractmethod
    def BorderWidth(self, value: float):
        """
        Sets the width of the border.
        """
        pass

    @property
    @abc.abstractmethod
    def HighlightMode(self) -> 'PdfHighlightMode':
        """
        Gets or sets the highlighting mode.
        """
        pass

    @HighlightMode.setter
    @abc.abstractmethod
    def HighlightMode(self, value: 'PdfHighlightMode'):
        """
        Sets the highlighting mode.
        """
        pass

    @property
    @abc.abstractmethod
    def Font(self) -> 'PdfFontBase':
        """
        Gets or sets the font.
        """
        pass

    @Font.setter
    @abc.abstractmethod
    def Font(self, value: 'PdfFontBase'):
        """
        Sets the font.
        """
        pass

    @property
    @abc.abstractmethod
    def TextAlignment(self) -> 'PdfTextAlignment':
        """
        Gets or sets the text alignment.
        """
        pass

    @TextAlignment.setter
    @abc.abstractmethod
    def TextAlignment(self, value: 'PdfTextAlignment'):
        """
        Sets the text alignment.
        """
        pass

    @property
    @abc.abstractmethod
    def Actions(self) -> 'PdfFieldActions':
        """
        Gets the actions of the field.
        """
        pass

    @property
    @abc.abstractmethod
    def BorderStyle(self) -> 'PdfBorderStyle':
        """
        Gets or sets the border style.
        """
        pass

    @BorderStyle.setter
    @abc.abstractmethod
    def BorderStyle(self, value: 'PdfBorderStyle'):
        """
        Sets the border style.
        """
        pass

    @property
    @abc.abstractmethod
    def Visible(self) -> bool:
        """
        Gets or sets a value indicating whether this field is visible.
        """
        pass

    @Visible.setter
    @abc.abstractmethod
    def Visible(self, value: bool):
        """
        Sets the value indicating whether this field is visible.
        """
        pass

    @property
    @abc.abstractmethod
    def Name(self) -> str:
        """
        Gets the name.
        """
        pass

    @property
    @abc.abstractmethod
    def Form(self) -> 'PdfForm':
        """
        Gets the form.
        """
        pass

    @property
    @abc.abstractmethod
    def MappingName(self) -> str:
        """
        Gets or sets the mapping name to be used when exporting interactive form field data from the document.
        """
        pass

    @MappingName.setter
    @abc.abstractmethod
    def MappingName(self, value: str):
        """
        Sets the mapping name to be used when exporting interactive form field data from the document.
        """
        pass

    @property
    @abc.abstractmethod
    def Export(self) -> bool:
        """
        Gets or sets a value indicating whether this field is export.
        """
        pass

    @Export.setter
    @abc.abstractmethod
    def Export(self, value: bool):
        """
        Sets the value indicating whether this field is export.
        """
        pass

    @property
    @abc.abstractmethod
    def ReadOnly(self) -> bool:
        """
        Gets or sets a value indicating whether the field is read only.
        """
        pass

    @ReadOnly.setter
    @abc.abstractmethod
    def ReadOnly(self, value: bool):
        """
        Sets the value indicating whether the field is read only.
        """
        pass

    @property
    @abc.abstractmethod
    def Required(self) -> bool:
        """
        Gets or sets a value indicating whether this field is required.
        """
        pass

    @Required.setter
    @abc.abstractmethod
    def Required(self, value: bool):
        """
        Sets the value indicating whether this field is required.
        """
        pass

    @property
    @abc.abstractmethod
    def ToolTip(self) -> str:
        """
        Gets or sets the tool tip.
        """
        pass

    @ToolTip.setter
    @abc.abstractmethod
    def ToolTip(self, value: str):
        """
        Sets the tool tip.
        """
        pass

    @property
    @abc.abstractmethod
    def Page(self) -> 'PdfPageBase':
        """
        Gets the page.
        """
        pass

    @property
    @abc.abstractmethod
    def Flatten(self) -> bool:
        """
        Gets or sets a value indicating whether this field is flatten.
        """
        pass

    @Flatten.setter
    @abc.abstractmethod
    def Flatten(self, value: bool):
        """
        Sets the value indicating whether this field is flatten.
        """
        pass