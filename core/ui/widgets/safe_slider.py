from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QWidget
from qfluentwidgets import Slider


class SafeSlider(Slider):
    """Refined Fluent Slider that requires explicit left-click or drag to change values.

    Fixes an upstream QFluentWidgets issue where mouseMoveEvent updates the slider value
    even when no mouse buttons are pressed (e.g. during hover or tracking).
    Also disables wheelEvent to prevent accidental value alterations while scrolling.
    """

    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(orientation, parent=parent)

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            super().mousePressEvent(e)
        else:
            e.ignore()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.buttons() & Qt.MouseButton.LeftButton:
            super().mouseMoveEvent(e)
        else:
            e.ignore()

    def wheelEvent(self, e: QWheelEvent) -> None:  # noqa: N802
        # Do not alter slider on wheel scroll so the parent page scrolls smoothly
        e.ignore()
