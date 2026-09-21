"""Creates a clean release ZIP archive of dist/Jarvis for distribution."""

import sys
import zipfile
from pathlib import Path


def create_release_zip(version: str = "v0.1.0") -> Path:
    root_dir = Path(__file__).resolve().parent.parent
    dist_dir = root_dir / "dist"
    jarvis_dir = dist_dir / "Jarvis"

    if not jarvis_dir.exists():
        raise FileNotFoundError(f"Directory not found: {jarvis_dir}")

    zip_filename = f"Jarvis-{version}-windows-x64.zip"
    zip_path = dist_dir / zip_filename

    exclude_dirs = {"data", "logs", "__pycache__"}
    exclude_files = {".env", ".gitignore"}
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
    cli_version = sys.argv[1] if len(sys.argv) > 1 else "v0.1.0"
    create_release_zip(cli_version)
