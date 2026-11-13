"""Two-column Fluent ComboBox for voice selection with aligned model weight/status."""

from PySide6.QtCore import QModelIndex, QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QFontMetrics,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QPushButton, QSizePolicy, QStyleOptionViewItem, QWidget
from qfluentwidgets import ComboBox, FluentIcon, isDarkTheme
from qfluentwidgets.components.widgets.combo_box import ComboBoxMenu
from qfluentwidgets.components.widgets.menu import (
    IndicatorMenuItemDelegate,
    MenuAnimationType,
)

RIGHT_COLUMN_WIDTH = 96


def _split_two_columns(raw_text: str) -> tuple[str, str]:
    if "\t" in raw_text:
        left, right = raw_text.split("\t", 1)
        return left.strip(), right.strip()
    return raw_text.strip(), ""


def _right_column_color(right_text: str) -> QColor:
    if "✓" in right_text:
        return QColor("#4cc2ff")
    if "0 MB" in right_text or "Nativa" in right_text:
        return QColor("#8a909e")
    return QColor("#b0b7c6")


class TwoColumnVoiceMenuItemDelegate(IndicatorMenuItemDelegate):
    """Renders dropdown menu items in two aligned columns: Voice Name | Weight/Status."""

    def initStyleOption(  # noqa: N802
        self, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        super().initStyleOption(option, index)
        option.text = ""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        raw_text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        super().paint(painter, option, index)

        left_text, right_text = _split_two_columns(raw_text)
        rect: QRect = option.rect

        painter.save()
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        painter.setFont(option.font)
        fm = QFontMetrics(option.font)

        right_col_x = rect.right() - RIGHT_COLUMN_WIDTH - 10
        left_rect = QRect(
            rect.left() + 14,
            rect.top(),
            max(40, right_col_x - (rect.left() + 20)),
            rect.height(),
        )
        right_rect = QRect(
            right_col_x + 6,
            rect.top(),
            RIGHT_COLUMN_WIDTH - 6,
            rect.height(),
        )

        # Draw subtle column separator line
        sep_pen = QPen(QColor(255, 255, 255, 22), 1.0)
        painter.setPen(sep_pen)
        painter.drawLine(right_col_x, rect.top() + 7, right_col_x, rect.bottom() - 7)

        # Column 1: Voice Name (elided if needed)
        elided_left = fm.elidedText(
            left_text, Qt.TextElideMode.ElideRight, left_rect.width()
        )
        painter.setPen(QColor("#ededf0"))
        painter.drawText(
            left_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elided_left,
        )

        # Column 2: Model Size / Status (right-aligned)
        if right_text:
            painter.setPen(_right_column_color(right_text))
            painter.drawText(
                right_rect,
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                right_text,
            )

        painter.restore()


class TwoColumnVoiceComboBox(ComboBox):
    """Fluent ComboBox that keeps a bounded width and renders 2 columns (Name | Size)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(180)

    @staticmethod
    def split_columns(raw_text: str) -> tuple[str, str]:
        return _split_two_columns(raw_text)

    def setText(self, text: str) -> None:  # noqa: N802
        # Override ComboBoxBase.setText without calling self.adjustSize()
        # so long item labels never force the parent card wider than the window.
        QPushButton.setText(self, text)
        self.update()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(180, 33)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(260, 33)

    def _createComboMenu(self) -> ComboBoxMenu:  # noqa: N802
        menu = ComboBoxMenu(self)
        menu.view.setItemDelegate(TwoColumnVoiceMenuItemDelegate(menu.view))
        return menu

    def _showComboMenu(self) -> None:  # noqa: N802
        if not self.items:
            return

        menu = self._createComboMenu()
        for item in self.items:
            action = QAction(item.icon, item.text, menu)
            action.setEnabled(item.isEnabled)
            menu.addAction(action)

        menu.view.itemClicked.connect(
            lambda list_item: self._onItemClicked(menu.view.row(list_item))
        )

        min_menu_w = max(self.width(), 370)
        if menu.view.width() < min_menu_w:
            menu.view.setMinimumWidth(min_menu_w)
            menu.adjustSize()

        menu.setMaxVisibleItems(self.maxVisibleItems())
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.closedSignal.connect(self._onDropMenuClosed)
        self.dropMenu = menu

        if self.currentIndex() >= 0 and self.items:
            menu.setDefaultAction(menu.actions()[self.currentIndex()])

        x = (
            -menu.width() // 2
            + menu.layout().contentsMargins().left()
            + self.width() // 2
        )
        pd = self.mapToGlobal(QPoint(x, self.height()))
        hd = menu.view.heightForAnimation(pd, MenuAnimationType.DROP_DOWN)

        pu = self.mapToGlobal(QPoint(x, 0))
        hu = menu.view.heightForAnimation(pu, MenuAnimationType.PULL_UP)

        if hd >= hu:
            menu.view.adjustSize(pd, MenuAnimationType.DROP_DOWN)
            menu.exec(pd, ani=True, aniType=MenuAnimationType.DROP_DOWN)
        else:
            menu.view.adjustSize(pu, MenuAnimationType.PULL_UP)
            menu.exec(pu, ani=True, aniType=MenuAnimationType.PULL_UP)

    def paintEvent(self, e: QPaintEvent) -> None:  # noqa: N802
        saved_text = self.text()
        QPushButton.setText(self, "")
        QPushButton.paintEvent(self, e)
        QPushButton.setText(self, saved_text)

        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        if self.isHover:
            painter.setOpacity(0.88)
        elif self.isPressed:
            painter.setOpacity(0.75)

        left_text, right_text = _split_two_columns(saved_text)
        fm = QFontMetrics(self.font())

        arrow_space = 28
        right_col_x = self.width() - arrow_space - RIGHT_COLUMN_WIDTH
        left_rect = QRect(
            12,
            0,
            max(40, right_col_x - 18),
            self.height(),
        )
        right_rect = QRect(
            right_col_x + 6,
            0,
            RIGHT_COLUMN_WIDTH - 8,
            self.height(),
        )

        # Subtle vertical divider between Name and Weight/Status
        sep_pen = QPen(QColor(255, 255, 255, 22), 1.0)
        painter.setPen(sep_pen)
        painter.drawLine(right_col_x, 7, right_col_x, self.height() - 7)

        elided_left = fm.elidedText(
            left_text, Qt.TextElideMode.ElideRight, left_rect.width()
        )
        painter.setPen(QColor("#ededf0"))
        painter.drawText(
            left_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elided_left,
        )

        if right_text:
            painter.setPen(_right_column_color(right_text))
            painter.drawText(
                right_rect,
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                right_text,
            )

        arrow_rect = QRectF(
            self.width() - 22,
            self.height() / 2 - 5 + self.arrowAni.y,
            10,
            10,
        )
        if isDarkTheme():
            FluentIcon.ARROW_DOWN.render(painter, arrow_rect)
        else:
            FluentIcon.ARROW_DOWN.render(painter, arrow_rect, fill="#646464")
        painter.end()
