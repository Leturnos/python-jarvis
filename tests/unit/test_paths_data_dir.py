import sys
from unittest.mock import patch

from core.shared.paths import get_app_root, get_user_data_dir


def test_get_user_data_dir_development_mode(tmp_path, monkeypatch):
    """In non-frozen development mode, returns app_root / 'data'."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    data_dir = get_user_data_dir()
    assert data_dir == get_app_root() / "data"
    assert data_dir.exists()


def test_get_user_data_dir_frozen_mode(tmp_path, monkeypatch):
    """In frozen mode without portable.flag, returns %APPDATA%/Jarvis/data."""
    fake_appdata = tmp_path / "AppData" / "Roaming"
    fake_appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(fake_appdata))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    # Ensure no portable.flag in app_root
    portable_flag = get_app_root() / "portable.flag"
    if portable_flag.exists():
        portable_flag.unlink()

    data_dir = get_user_data_dir()
    expected = fake_appdata / "Jarvis" / "data"
    assert data_dir == expected
    assert data_dir.exists()


def test_get_user_data_dir_portable_mode(tmp_path, monkeypatch):
    """In frozen mode WITH portable.flag, returns app_root / 'data'."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    fake_app_root = tmp_path / "JarvisApp"
    fake_app_root.mkdir()
    (fake_app_root / "portable.flag").write_text("portable")

    with patch("core.shared.paths.get_app_root", return_value=fake_app_root):
        data_dir = get_user_data_dir()
        assert data_dir == fake_app_root / "data"
        assert data_dir.exists()


def test_get_user_data_dir_auto_migration(tmp_path, monkeypatch):
    """Migrates history.db and llm_cache.db from legacy app_root/data to %APPDATA%/Jarvis/data."""
    fake_appdata = tmp_path / "AppData" / "Roaming"
    fake_appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(fake_appdata))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    fake_app_root = tmp_path / "JarvisApp"
    legacy_data = fake_app_root / "data"
    legacy_data.mkdir(parents=True)

    # Create dummy legacy databases
    (legacy_data / "history.db").write_text("legacy history content")
    (legacy_data / "llm_cache.db").write_text("legacy cache content")

    with patch("core.shared.paths.get_app_root", return_value=fake_app_root):
        data_dir = get_user_data_dir()
        assert data_dir == fake_appdata / "Jarvis" / "data"
        # Check files migrated
        assert (data_dir / "history.db").read_text() == "legacy history content"
        assert (data_dir / "llm_cache.db").read_text() == "legacy cache content"


def test_get_user_data_dir_migration_does_not_overwrite_existing(tmp_path, monkeypatch):
    """Does not overwrite existing files in %APPDATA%/Jarvis/data during migration."""
    fake_appdata = tmp_path / "AppData" / "Roaming"
    target_data = fake_appdata / "Jarvis" / "data"
    target_data.mkdir(parents=True)
    (target_data / "history.db").write_text("new history content")

    monkeypatch.setenv("APPDATA", str(fake_appdata))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    fake_app_root = tmp_path / "JarvisApp"
    legacy_data = fake_app_root / "data"
    legacy_data.mkdir(parents=True)
    (legacy_data / "history.db").write_text("legacy history content")

    with patch("core.shared.paths.get_app_root", return_value=fake_app_root):
        data_dir = get_user_data_dir()
        assert (data_dir / "history.db").read_text() == "new history content"


def test_get_app_version_dynamically_reads_pyproject(tmp_path):
    from core.shared.paths import get_app_version

    fake_root = tmp_path / "JarvisApp"
    fake_root.mkdir()
    pyproject = fake_root / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "1.5.42"\n', encoding="utf-8")

    with patch("core.shared.paths.get_app_root", return_value=fake_root):
        assert get_app_version() == "1.5.42"
