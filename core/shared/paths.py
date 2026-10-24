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


def get_user_config_path(app_root: Path | None = None) -> Path:
    """Returns the path to config.yaml.

    - In frozen mode without 'portable.flag', resolves to %APPDATA%/Jarvis/config.yaml.
      If missing in APPDATA, automatically seeds it from app_root/config.yaml.
    - In development mode or with 'portable.flag', resolves to app_root/config.yaml.
    """
    base_root = app_root or get_app_root()
    is_frozen = getattr(sys, "frozen", False)
    is_portable = (base_root / "portable.flag").exists()

    if is_frozen and not is_portable and "APPDATA" in os.environ:
        target_dir = Path(os.environ["APPDATA"]) / "Jarvis"
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        target_config = target_dir / "config.yaml"
        source_config = base_root / "config.yaml"
        if not target_config.exists() and source_config.exists():
            try:
                shutil.copy2(source_config, target_config)
            except OSError:
                pass
        if target_config.exists():
            return target_config
        if source_config.exists():
            return source_config
        return target_config

    return base_root / "config.yaml"


def get_log_dir(app_root: Path | None = None) -> Path:
    """Returns the directory for application logs.

    - In frozen mode without 'portable.flag', resolves to %APPDATA%/Jarvis/logs.
      Automatically migrates legacy log files from app_root/logs if present.
    - In development mode or with 'portable.flag', resolves to app_root/logs.
    """
    base_root = app_root or get_app_root()
    is_frozen = getattr(sys, "frozen", False)
    is_portable = (base_root / "portable.flag").exists()

    if is_frozen and not is_portable and "APPDATA" in os.environ:
        target_dir = Path(os.environ["APPDATA"]) / "Jarvis" / "logs"
    else:
        target_dir = base_root / "logs"

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    # Automatic migration from legacy local logs folder if running in APPDATA mode
    legacy_dir = base_root / "logs"
    if target_dir != legacy_dir and legacy_dir.exists():
        _migrate_legacy_logs(legacy_dir, target_dir)

    return target_dir


def _migrate_legacy_logs(legacy_dir: Path, target_dir: Path) -> None:
    """Safely copies legacy log files without overwriting existing target log files."""
    try:
        for log_file in legacy_dir.glob("*.log*"):
            target_file = target_dir / log_file.name
            if not target_file.exists():
                try:
                    shutil.copy2(log_file, target_file)
                except OSError:
                    pass
    except OSError:
        pass
