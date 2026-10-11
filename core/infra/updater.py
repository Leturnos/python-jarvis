import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError

from core.infra.config import config
from core.infra.logger_config import logger
from core.shared.paths import get_app_root, get_app_version


def normalize_repo(repo: str) -> str:
    """Normalizes a GitHub repo string into 'owner/repo'.

    Supports both full URL ('https://github.com/owner/repo') and shorthand ('owner/repo').
    """
    clean = repo.strip()
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if clean.startswith(prefix):
            clean = clean[len(prefix) :]
            break
    clean = clean.removesuffix(".git").strip("/")
    return clean


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parses a version string (e.g. 'v0.2.1', '1.0.0') into a numeric tuple."""
    clean = version_str.strip().lstrip("vV")
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", clean)
    if not match:
        return (0, 0, 0)
    parts = [int(p) if p is not None else 0 for p in match.groups()]
    return tuple(parts)


@dataclass
class ReleaseInfo:
    version: str
    title: str
    body: str
    html_url: str
    download_url: str
    asset_name: str
    asset_size: int
    has_update: bool


class UpdateManager:
    """Handles GitHub release querying, asset downloading, and detached binary replacement."""

    def __init__(
        self,
        current_version: str | None = None,
        repo: str | None = None,
        temp_dir: Path | str | None = None,
    ) -> None:
        self.current_version = current_version or get_app_version()
        update_cfg = config.get("updates", {})
        raw_repo = repo or update_cfg.get("github_repo", "Leturnos/python-jarvis")
        self.repo = normalize_repo(raw_repo)

        if temp_dir is not None:
            self.temp_dir = Path(temp_dir)
        else:
            self.temp_dir = Path(tempfile.gettempdir()) / "JarvisUpdate"

        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def check_for_updates(self, timeout: float = 8.0) -> ReleaseInfo | None:
        """Queries GitHub Releases API for the latest release."""
        api_url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        req = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": f"Jarvis-App-Updater/{self.current_version}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))

            tag_name: str = payload.get("tag_name", "")
            title: str = payload.get("name") or tag_name
            body: str = payload.get("body", "")
            html_url: str = payload.get("html_url", "")
            assets: list[dict[str, object]] = payload.get("assets", [])

            # Locate Windows zip asset
            download_url = ""
            asset_name = ""
            asset_size = 0

            for asset in assets:
                name = str(asset.get("name", ""))
                if "windows" in name.lower() or name.lower().endswith(".zip"):
                    asset_name = name
                    download_url = str(asset.get("browser_download_url", ""))
                    asset_size = int(str(asset.get("size", 0)))
                    break

            latest_parsed = parse_version(tag_name)
            current_parsed = parse_version(self.current_version)
            has_update = latest_parsed > current_parsed

            return ReleaseInfo(
                version=tag_name,
                title=title,
                body=body,
                html_url=html_url,
                download_url=download_url,
                asset_name=asset_name,
                asset_size=asset_size,
                has_update=has_update,
            )
        except (URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to check for updates from {api_url}: {e}")
            return None

    def download_asset(
        self,
        url: str,
        dest_path: Path | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        chunk_size: int = 65536,
    ) -> Path:
        """Downloads release asset file with optional progress reporting."""
        target = dest_path or (self.temp_dir / "update_package.zip")
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"Jarvis-App-Updater/{self.current_version}"},
        )

        with urllib.request.urlopen(req) as resp, open(target, "wb") as out_file:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total_size)

        return target

    def extract_archive(self, zip_path: Path, extract_dir: Path | None = None) -> Path:
        """Extracts ZIP release package and returns the directory containing updated files."""
        target_dir = extract_dir or (self.temp_dir / "extracted")
        target_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)

        # If zip packaged an inner 'Jarvis' root folder, point directly inside it
        nested_jarvis = target_dir / "Jarvis"
        if nested_jarvis.is_dir() and (nested_jarvis / "Jarvis.exe").exists():
            return nested_jarvis

        return target_dir

    def generate_batch_script(
        self,
        pid: int,
        source_dir: Path,
        dest_dir: Path,
        exe_path: Path,
    ) -> Path:
        """Generates an external batch script to wait for Jarvis exit, sync files, and restart."""
        script_path = self.temp_dir / "updater.bat"
        # Windows batch file to sync binaries while avoiding open file locks
        script_content = f"""@echo off
setlocal enabledelayedexpansion

echo [Jarvis Updater] Aguardando encerramento do processo PID {pid}...
:wait_loop
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_loop
)

echo [Jarvis Updater] Copiando novos arquivos para {dest_dir}...
robocopy "{source_dir}" "{dest_dir}" /E /XD data logs .git /XF .env config.yaml portable.flag /NFL /NDL /NJH /NJS /nc /ns /np
if %ERRORLEVEL% LEQ 7 (
    echo [Jarvis Updater] Atualizacao concluida com sucesso!
) else (
    echo [Jarvis Updater] Falha ao copiar arquivos: erro %ERRORLEVEL%
)

echo [Jarvis Updater] Reiniciando Jarvis...
start "" "{exe_path}"

exit /b 0
"""
        script_path.write_text(script_content, encoding="utf-8")
        return script_path

    def apply_update_and_restart(
        self,
        source_dir: Path,
        dest_dir: Path | None = None,
        exe_path: Path | None = None,
    ) -> None:
        """Launches the external updater script and requests immediate application exit."""
        target_dest = dest_dir or get_app_root()
        target_exe = exe_path or (target_dest / "Jarvis.exe")
        current_pid = os.getpid()

        script_path = self.generate_batch_script(
            pid=current_pid,
            source_dir=source_dir,
            dest_dir=target_dest,
            exe_path=target_exe,
        )

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(
                subprocess, "DETACHED_PROCESS", 0x00000008
            )

        subprocess.Popen(
            [str(script_path)],
            creationflags=creation_flags,
            close_fds=True,
            shell=True,
        )
