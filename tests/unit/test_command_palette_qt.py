from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from core.ui.command_palette_qt import QtCommandPalette


def test_command_palette_qt_filtering():
    _ = QApplication.instance() or QApplication([])
    dispatcher = MagicMock()
    palette = QtCommandPalette(dispatcher)

    palette.all_commands = [
        {
            "label": "[Plugin] media_control - Control Media",
            "action_type": "plugin",
            "intent": "media_control",
            "risk_level": "safe",
        },
        {
            "label": "[Histórico] abrir spotify",
            "action_type": "history",
            "command_text": "abrir spotify",
            "intent": "system_cmd",
            "risk_level": "safe",
        },
    ]
    palette._filter_commands("spotify")

    assert len(palette.filtered_commands) == 1
    assert palette.filtered_commands[0]["command_text"] == "abrir spotify"
