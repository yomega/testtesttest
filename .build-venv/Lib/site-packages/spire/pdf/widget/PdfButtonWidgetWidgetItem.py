from enum import Enum
from plum import dispatch
from typing import TypeVar, Union, Generic, List, Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class PdfButtonWidgetWidgetItem(PdfFieldWidgetItem):
    """
    Represents button group item of an existing PDF document's form.
    """

    def __init__(self, field: PdfField, index: int):
        """
        Initializes a new instance of the PdfButtonWidgetWidgetItem class.

        Args:
            field (PdfField): The parent field of the button group item.
            index (int): The index of the button group item.
        """
        super().__init__(field)
        self.index = index

    @property
    def value(self) -> str:
        """
        Gets or sets the value of the button group item.

        Returns:
            str: The value of the button group item.
        """
        return self.field.get_button_widget_item_value(self.index)

    @value.setter
    def value(self, value: str):
        """
        Sets the value of the button group item.

        Args:
            value (str): The value to set for the button group item.
        """
        self.field.set_button_widget_item_value(self.index, value)

    @property
    def selected(self) -> bool:
        """
        Gets or sets a value indicating whether the button group item is selected.

        Returns:
            bool: True if the button group item is selected; otherwise, False.
        """
        return self.field.is_button_widget_item_selected(self.index)

    @selected.setter
    def selected(self, value: bool):
        """
        Sets a value indicating whether the button group item is selected.

        Args:
            value (bool): True to select the button group item; otherwise, False.
        """
        self.field.set_button_widget_item_selected(self.index, value)