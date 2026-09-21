from pathlib import Path
from unittest.mock import patch

from core.cache.sqlite_cache import SQLiteLLMCache
from core.media.providers.spotify import SpotifyProvider
from core.plugins.macro_manager import MacroManager
from core.plugins.plugin_manager import PluginManager
from core.shared.paths import get_app_root
from core.shared.sqlite_base import SQLiteBase


def test_plugin_manager_resolves_against_app_root_when_cwd_is_arbitrary(
    tmp_path, monkeypatch
):
    # Simulate Windows Startup Registry running from C:\Windows\System32 (or arbitrary dir)
    fake_system32 = tmp_path / "system32"
    fake_system32.mkdir()
    monkeypatch.chdir(fake_system32)

    assert Path.cwd() == fake_system32

    # Default arguments resolve to app_root / "plugins"
    pm = PluginManager()
    app_root = get_app_root()
    expected_plugins_dir = str(app_root / "plugins")
    assert pm.plugins_dir == expected_plugins_dir
    assert not (fake_system32 / "plugins").exists()


def test_plugin_manager_custom_paths(tmp_path, monkeypatch):
    fake_system32 = tmp_path / "system32"
    fake_system32.mkdir()
    monkeypatch.chdir(fake_system32)

    # 1. Custom relative path resolves against get_app_root()
    pm_rel = PluginManager(plugins_dir="custom_plugins")
    assert pm_rel.plugins_dir == str(get_app_root() / "custom_plugins")
    assert not (fake_system32 / "custom_plugins").exists()

    # 2. Custom absolute path is preserved as-is
    abs_plugins = tmp_path / "abs_plugins"
    abs_plugins.mkdir()
    pm_abs = PluginManager(plugins_dir=abs_plugins)
    assert pm_abs.plugins_dir == str(abs_plugins)


def test_macro_manager_resolves_against_app_root_when_cwd_is_arbitrary(
    tmp_path, monkeypatch
):
    fake_system32 = tmp_path / "system32"
    fake_system32.mkdir()
    monkeypatch.chdir(fake_system32)

    mm = MacroManager()
    expected_macros_path = str(get_app_root() / "plugins" / "macros.yaml")
    assert mm.macros_path == expected_macros_path
    assert not (fake_system32 / "plugins").exists()


def test_macro_manager_custom_paths(tmp_path, monkeypatch):
    fake_system32 = tmp_path / "system32"
    fake_system32.mkdir()
    monkeypatch.chdir(fake_system32)

    # 1. Custom relative path resolves against get_app_root()
    mm_rel = MacroManager(macros_path="custom/macro.yaml")
    assert mm_rel.macros_path == str(get_app_root() / "custom" / "macro.yaml")

    # 2. Custom absolute path is preserved as-is
    abs_macro = tmp_path / "custom_macro.yaml"
    mm_abs = MacroManager(macros_path=abs_macro)
    assert mm_abs.macros_path == str(abs_macro)


def test_sqlite_cache_resolves_against_app_root_when_cwd_is_arbitrary(
    tmp_path, monkeypatch
):
    fake_system32 = tmp_path / "system32"
    fake_system32.mkdir()
    monkeypatch.chdir(fake_system32)

    # Mock _init_db to avoid writing to real data/llm_cache.db in unit test
    with patch.object(SQLiteLLMCache, "_init_db"):
        cache = SQLiteLLMCache()
        expected_db_path = str(get_app_root() / "data" / "llm_cache.db")
        assert cache.db_path == expected_db_path
        assert not (fake_system32 / "data").exists()


def test_sqlite_cache_in_memory():
    # Verify that in-memory cache connections work without OperationalError
    cache = SQLiteLLMCache(db_path=":memory:")
    assert cache.db_path == ":memory:"
    with cache.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


def test_sqlite_base_resolves_relative_paths_against_app_root(tmp_path, monkeypatch):
    fake_system32 = tmp_path / "system32"
    fake_system32.mkdir()
    monkeypatch.chdir(fake_system32)

    # Use a mock or isolated name
    base = SQLiteBase(tmp_path / "isolated.db")
    assert base.db_path == str(tmp_path / "isolated.db")

    # Relative path
    base_rel = SQLiteBase("isolated_rel.db")
    assert base_rel.db_path == str(get_app_root() / "isolated_rel.db")
    assert not (fake_system32 / "isolated_rel.db").exists()


def test_sqlite_base_supports_memory_database():
    base = SQLiteBase(":memory:")
    assert base.db_path == ":memory:"
    with base.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE test_mem (id INT);")
        cursor.execute("INSERT INTO test_mem VALUES (42);")
        cursor.execute("SELECT id FROM test_mem;")
        assert cursor.fetchone() == (42,)


def test_spotify_provider_resolves_against_app_root_when_cwd_is_arbitrary(
    tmp_path, monkeypatch
):
    fake_system32 = tmp_path / "system32"
    fake_system32.mkdir()
    monkeypatch.chdir(fake_system32)

    sp = SpotifyProvider()
    expected_playlists_path = str(get_app_root() / "data" / "media" / "playlists.json")
    assert sp.playlists_path == expected_playlists_path
    assert not (fake_system32 / "data").exists()
