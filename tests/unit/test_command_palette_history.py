from unittest.mock import MagicMock, patch
from core.persistence.history_db import HistoryManager


def test_get_recent_commands_returns_unique_list():
    with patch.object(HistoryManager, "_init_db"), patch(
        "threading.Thread.start"
    ):
        db_manager = HistoryManager(db_path=":memory:")
        db_manager.get_connection = MagicMock()

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("abrir vscode",),
            ("tocar spotify",),
            ("abrir vscode",),
            ("abrir warp",),
        ]
        db_manager.get_connection.return_value.__enter__.return_value.cursor.return_value = (
            mock_cursor
        )

        recent = db_manager.get_recent_commands(limit=10)
        assert recent == ["abrir vscode", "tocar spotify", "abrir warp"]
