"""Creates a clean release ZIP archive of dist/Jarvis for distribution."""

import sys
import zipfile
from pathlib import Path


def get_default_version() -> str:
    try:
        from core.shared.paths import get_app_version

        ver = get_app_version()
        if ver and ver != "0.0.0":
            return f"v{ver}" if not ver.startswith("v") else ver
    except Exception:
        pass

    return "v0.0.0"


def create_release_zip(
    version: str | None = None,
    dist_dir: Path | None = None,
    versioned_name: bool = False,
) -> Path:
    if version is None:
        version = get_default_version()
    root_dir = Path(__file__).resolve().parent.parent
    base_dist = dist_dir or (root_dir / "dist")
    jarvis_dir = base_dist / "Jarvis"

    if not jarvis_dir.exists():
        raise FileNotFoundError(f"Directory not found: {jarvis_dir}")

    if versioned_name or "--versioned" in sys.argv:
        zip_filename = f"Jarvis-{version}-windows-x64.zip"
    else:
        zip_filename = "Jarvis-windows-x64.zip"

    zip_path = base_dist / zip_filename

    exclude_dirs = {"data", "logs", "__pycache__"}
    exclude_files = {".env", ".gitignore", ".first_run_completed"}
    exclude_extensions = {".log", ".db", ".db-wal", ".db-shm", ".pyc"}

    print(f"Creating release archive: {zip_path}...")
    file_count = 0

    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as zf:
        for path in jarvis_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.name in exclude_files or path.suffix.lower() in exclude_extensions:
                continue
            rel = path.relative_to(jarvis_dir)
            if any(part in exclude_dirs for part in rel.parts):
                continue
            arcname = Path("Jarvis") / rel
            zf.write(path, arcname=str(arcname))
            file_count += 1

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Successfully packaged {file_count} files into {zip_path.name}")
    print(f"Archive size: {size_mb:.2f} MB")
    return zip_path


if __name__ == "__main__":
    cli_version = sys.argv[1] if len(sys.argv) > 1 else get_default_version()
    create_release_zip(cli_version)
