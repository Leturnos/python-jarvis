from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QWidget

SCREEN_POSITIONS_ORDER: list[str] = [
    "top_left",
    "top_center",
    "top_right",
    "center",
    "bottom_left",
    "bottom_center",
    "bottom_right",
]

SCREEN_POSITION_LABELS: dict[str, str] = {
    "top_left": "↖ Superior Esquerdo",
    "top_center": "⬆ Superior Central",
    "top_right": "↗ Superior Direito",
    "center": "🎯 Centro da Tela",
    "bottom_left": "↙ Inferior Esquerdo",
    "bottom_center": "⬇ Inferior Central",
    "bottom_right": "↘ Inferior Direito",
}


def calculate_screen_position(
    screen_geo: QRect,
    widget_width: int,
    widget_height: int,
    position_key: str,
    margin_x: int = 28,
    margin_y: int = 36,
) -> QPoint:
    """Calculates target (x, y) coordinates on a screen geometry for a given position key."""
    pos = position_key if position_key in SCREEN_POSITIONS_ORDER else "top_center"

    left_x = screen_geo.x() + margin_x
    center_x = screen_geo.x() + (screen_geo.width() - widget_width) // 2
    right_x = screen_geo.x() + screen_geo.width() - widget_width - margin_x

    top_y = screen_geo.y() + margin_y
    center_y = screen_geo.y() + (screen_geo.height() - widget_height) // 2
    bottom_y = screen_geo.y() + screen_geo.height() - widget_height - margin_y

    mapping: dict[str, tuple[int, int]] = {
        "top_left": (left_x, top_y),
        "top_center": (center_x, top_y),
        "top_right": (right_x, top_y),
        "center": (center_x, center_y),
        "bottom_left": (left_x, bottom_y),
        "bottom_center": (center_x, bottom_y),
        "bottom_right": (right_x, bottom_y),
    }

    x, y = mapping.get(pos, (center_x, top_y))
    return QPoint(x, y)


def reposition_on_screen(
    widget: QWidget,
    position_key: str,
    margin_x: int = 28,
    margin_y: int = 36,
) -> QPoint:
    """Moves a widget to the configured screen position on the primary screen."""
    screen = QApplication.primaryScreen()
    if screen is None:
        return widget.pos()
    geo = screen.availableGeometry()
    target = calculate_screen_position(
        geo,
        widget.width(),
        widget.height(),
        position_key,
        margin_x=margin_x,
        margin_y=margin_y,
    )
    widget.move(target)
    return target
