from pathlib import Path
from unittest.mock import patch

from core.infra.first_run import (
    is_first_run,
    mark_first_run_completed,
)


def test_is_first_run_true_when_marker_missing(tmp_path: Path):
    marker = tmp_path / "data" / ".first_run_completed"
    with patch("core.infra.first_run.get_first_run_marker_path", return_value=marker):
        assert is_first_run() is True


def test_mark_first_run_completed_creates_marker(tmp_path: Path):
    marker = tmp_path / "data" / ".first_run_completed"
    with patch("core.infra.first_run.get_first_run_marker_path", return_value=marker):
        assert is_first_run() is True
        mark_first_run_completed()
        assert marker.exists() is True
        assert is_first_run() is False


def test_is_first_run_false_when_marker_exists(tmp_path: Path):
    marker = tmp_path / "data" / ".first_run_completed"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("2026-09-23 12:00:00", encoding="utf-8")

    with patch("core.infra.first_run.get_first_run_marker_path", return_value=marker):
        assert is_first_run() is False
