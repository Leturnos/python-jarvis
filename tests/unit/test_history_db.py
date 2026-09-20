import tempfile
from pathlib import Path
from unittest.mock import patch

from core.persistence.history_db import HistoryManager


def test_history_manager_default_path_uses_app_root():
    with tempfile.TemporaryDirectory() as temp_dir:
        fake_root = Path(temp_dir)
        with patch("core.persistence.history_db.get_app_root", return_value=fake_root):
            with patch.dict(
                "core.persistence.history_db.config",
                {"paths": {"data_dir": "custom_data"}},
            ):
                hm = HistoryManager(db_path=None)
                try:
                    expected_db_path = str(fake_root / "custom_data" / "history.db")
                    assert (
                        Path(hm.db_path).resolve() == Path(expected_db_path).resolve()
                    )
                    assert (fake_root / "custom_data").is_dir()
                finally:
                    hm.close()
