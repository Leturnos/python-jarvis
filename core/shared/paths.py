import os
import shutil
import sys
from pathlib import Path


def get_app_root() -> Path:
    """Returns the base application directory whether running from source or frozen binary."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.absolute()
    return Path(__file__).parent.parent.parent.absolute()


def get_app_version() -> str:
    """Dynamically reads and returns the application version from pyproject.toml."""
    pyproject_path = get_app_root() / "pyproject.toml"
    if pyproject_path.exists():
        try:
            import tomllib

            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                version = data.get("project", {}).get("version")
                if version:
                    return str(version)
        except Exception:
            pass

    try:
        from importlib.metadata import version

        return str(version("python-jarvis"))
    except Exception:
        pass

    return "0.0.0"


def get_user_data_dir() -> Path:
    """Returns the directory for persistent user data (history, cache, user preferences).

    - In frozen mode (compiled binary) without 'portable.flag', resolves to
      %APPDATA%/Jarvis/data. Automatically migrates legacy database files from
      app_root/data if present.
    - If 'portable.flag' is found in app root or running in development mode,
      resolves to app_root/data.
    """
    app_root = get_app_root()
    is_frozen = getattr(sys, "frozen", False)
    is_portable = (app_root / "portable.flag").exists()

    if is_frozen and not is_portable and "APPDATA" in os.environ:
        target_dir = Path(os.environ["APPDATA"]) / "Jarvis" / "data"
    else:
        target_dir = app_root / "data"

    target_dir.mkdir(parents=True, exist_ok=True)

    # Automatic migration from legacy local data folder if running in APPDATA mode
    legacy_dir = app_root / "data"
    if target_dir != legacy_dir and legacy_dir.exists():
        _migrate_legacy_data(legacy_dir, target_dir)

    return target_dir


def _migrate_legacy_data(legacy_dir: Path, target_dir: Path) -> None:
    """Safely copies legacy database and state files without overwriting existing target files."""
    migration_targets = [
        "history.db",
        "history.db-wal",
        "history.db-shm",
        "llm_cache.db",
        "llm_cache.db-wal",
        "llm_cache.db-shm",
        ".first_run_completed",
    ]
    for filename in migration_targets:
        source_file = legacy_dir / filename
        target_file = target_dir / filename
        if source_file.exists() and not target_file.exists():
            try:
                shutil.copy2(source_file, target_file)
            except OSError:
                pass
