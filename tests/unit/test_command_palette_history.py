from unittest.mock import MagicMock, patch

from core.persistence.history_db import HistoryManager


def test_get_recent_commands_returns_unique_list():
    with patch.object(HistoryManager, "_init_db"), patch("threading.Thread.start"):
        db_manager = HistoryManager(db_path=":memory:")
        db_manager.get_connection = MagicMock()

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("abrir vscode",),
            ("tocar spotify",),
            ("abrir vscode",),
            ("abrir warp",),
        ]
        db_manager.get_connection.return_value.__enter__.return_value.cursor.return_value = mock_cursor

        recent = db_manager.get_recent_commands(limit=10)
        assert recent == ["abrir vscode", "tocar spotify", "abrir warp"]


def test_command_palette_fetches_expanded_history_limit():
    from core.ui.command_palette_qt import QtCommandPalette

    dispatcher = MagicMock()
    palette = QtCommandPalette(dispatcher)

    with (
        patch("core.ui.command_palette_qt.plugin_manager.get_intents", return_value=[]),
        patch(
            "core.ui.command_palette_qt.history_manager.get_recent_commands"
        ) as mock_get_cmds,
    ):
        mock_get_cmds.return_value = [f"cmd_{i}" for i in range(15)]
        palette._fetch_commands()

        mock_get_cmds.assert_called_once_with(limit=15)
        history_items = [
            c for c in palette.all_commands if c["action_type"] == "history"
        ]
        assert len(history_items) == 15
