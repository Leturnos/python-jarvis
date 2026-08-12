from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from core.ui.command_palette_qt import QtCommandPalette, QtCommandPaletteDialog


def test_command_palette_qt_filtering():
    _ = QApplication.instance() or QApplication([])
    dispatcher = MagicMock()
    palette = QtCommandPalette(dispatcher)

    palette.all_commands = [
        {
            "label": "🔌 media_control — Control Media",
            "action_type": "plugin",
            "intent": "media_control",
            "risk_level": "safe",
        },
        {
            "label": "🕒 abrir spotify",
            "action_type": "history",
            "command_text": "abrir spotify",
            "intent": "system_cmd",
            "risk_level": "safe",
        },
    ]
    palette._filter_commands("spotify")

    assert len(palette.filtered_commands) == 1
    assert palette.filtered_commands[0]["command_text"] == "abrir spotify"


def test_command_palette_qt_categories_ordering():
    _ = QApplication.instance() or QApplication([])
    dispatcher = MagicMock()
    palette = QtCommandPalette(dispatcher)

    palette.all_commands = [
        {
            "label": "🕒 abrir spotify",
            "action_type": "history",
            "command_text": "abrir spotify",
        },
        {
            "label": "🔌 media_control",
            "action_type": "plugin",
            "intent": "media_control",
            "risk_level": "safe",
        },
    ]
    palette.filtered_commands = palette.all_commands.copy()

    dialog = QtCommandPaletteDialog(palette)
    dialog._refresh_list()

    # Plugins section should be added first
    assert dialog.list_widget.item(0).text() == "── PLUGINS E INTENTS ──"
    assert "media_control" in dialog.list_widget.item(1).text()
    assert dialog.list_widget.item(2).text() == "── HISTÓRICO RECENTE ──"
    assert "abrir spotify" in dialog.list_widget.item(3).text()
