"""Secure manager for downloading, verifying, and cleaning up neural TTS voice packs.

Enforces HTTPS host allowlisting, strict file size caps, cryptographic checksum
verification (SHA-256 / MD5), and JSON config schema validation before any model
is made available to the TTS engine.
"""

import hashlib
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

import certifi

from core.audio.voice_catalog import (
    MODEL_ASSETS,
    VoiceModelAsset,
    get_voice_preset,
)
from core.infra.logger_config import logger
from core.shared.errors import SecurityError
from core.shared.paths import get_app_version, get_user_data_dir

ALLOWED_VOICE_DOMAINS: tuple[str, ...] = ("huggingface.co", "hf.co")
ALLOWED_VOICE_HOSTS: frozenset[str] = frozenset(ALLOWED_VOICE_DOMAINS)
MAX_ONNX_BYTES: int = 80 * 1024 * 1024  # 80 MB hard ceiling
MAX_JSON_BYTES: int = 64 * 1024  # 64 KB hard ceiling
MIN_ONNX_BYTES: int = 1 * 1024 * 1024  # 1 MB minimum sanity floor


class VoiceManager:
    """Manages local storage, integrity checks, and cleanup of neural voice models."""

    def __init__(self, voices_dir: Path | str | None = None) -> None:
        if voices_dir is not None:
            self.voices_dir = Path(voices_dir).resolve()
        else:
            self.voices_dir = (get_user_data_dir() / "voices").resolve()
        try:
            self.voices_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def _safe_path(self, filename: str) -> Path:
        """Resolves a filename inside voices_dir and blocks any path traversal attempt."""
        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            raise SecurityError(f"Invalid voice filename rejected: {filename!r}")
        resolved = (self.voices_dir / filename).resolve()
        if not resolved.is_relative_to(self.voices_dir):
            raise SecurityError(f"Path traversal detected for voice file: {filename!r}")
        return resolved

    @staticmethod
    def is_allowed_voice_host(host: str) -> bool:
        """Returns True if host is huggingface.co, hf.co, or an official subdomain (e.g. us.aws.cdn.hf.co)."""
        clean_host = (host or "").strip().lower().rstrip(".")
        if not clean_host:
            return False
        return any(
            clean_host == domain or clean_host.endswith(f".{domain}")
            for domain in ALLOWED_VOICE_DOMAINS
        )

    @classmethod
    def validate_download_url(cls, url: str) -> None:
        """Ensures the download URL uses HTTPS and points to an allowlisted Hugging Face / CDN host."""
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme.lower() != "https":
            raise SecurityError(f"Insecure voice download protocol blocked: {url}")
        host = (parsed.hostname or "").lower()
        if not cls.is_allowed_voice_host(host):
            raise SecurityError(
                f"Untrusted voice download host blocked: {host!r} (allowed: {list(ALLOWED_VOICE_DOMAINS)})"
            )

    @staticmethod
    def format_user_error(exc: Exception | str) -> str:
        """Converts technical download/security exceptions into clear PT-BR user messages."""
        if isinstance(exc, urllib.error.HTTPError):
            return (
                f"O servidor de vozes retornou erro HTTP {exc.code}. "
                "Tente novamente em instantes."
            )
        if isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError)):
            return (
                "Não foi possível conectar ao servidor de vozes. "
                "Verifique sua internet e tente novamente."
            )

        raw = str(exc).strip()
        lower = raw.lower()

        if (
            "untrusted voice download host" in lower
            or "insecure voice download" in lower
        ):
            return (
                "Download bloqueado por segurança: redirecionamento para "
                "domínio não reconhecido."
            )
        if (
            "integrity check failed" in lower
            or "size mismatch" in lower
            or "out of safe bounds" in lower
            or "exceeded safety limit" in lower
        ):
            return (
                "O arquivo baixado falhou na verificação de integridade "
                "(download incompleto ou corrompido). Tente novamente."
            )
        if "schema validation failed" in lower or "invalid json" in lower:
            return "O arquivo de configuração da voz é inválido e foi recusado."
        if (
            "urlopen error" in lower
            or "timed out" in lower
            or "getaddrinfo" in lower
            or "connection" in lower
        ):
            return (
                "Falha de conexão durante o download da voz. "
                "Verifique sua internet e tente novamente."
            )
        if isinstance(exc, OSError) or "permission" in lower or "winerror" in lower:
            return (
                "Não foi possível salvar a voz no disco. "
                "Verifique o espaço livre e permissões."
            )
        if len(raw) > 110:
            return raw[:107] + "..."
        return raw or "Erro inesperado ao baixar o pacote de voz."

    @staticmethod
    def compute_digests(file_path: Path) -> tuple[str, str, int]:
        """Computes (sha256_hex, md5_hex, size_bytes) in a single streaming pass."""
        sha256_hasher = hashlib.sha256()
        md5_hasher = hashlib.md5()
        total_bytes = 0
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha256_hasher.update(chunk)
                md5_hasher.update(chunk)
                total_bytes += len(chunk)
        return (
            sha256_hasher.hexdigest().lower(),
            md5_hasher.hexdigest().lower(),
            total_bytes,
        )

    @classmethod
    def verify_onnx_file(cls, onnx_path: Path, asset: VoiceModelAsset) -> None:
        """Verifies byte size and cryptographic digest of a downloaded .onnx model."""
        if not onnx_path.exists():
            raise SecurityError(f"Missing ONNX model file: {onnx_path.name}")

        sha256_hex, md5_hex, size_bytes = cls.compute_digests(onnx_path)
        if size_bytes < MIN_ONNX_BYTES or size_bytes > MAX_ONNX_BYTES:
            raise SecurityError(
                f"ONNX file size out of safe bounds ({size_bytes} bytes) for {asset.onnx_filename}"
            )

        if (
            asset.expected_onnx_bytes is not None
            and size_bytes != asset.expected_onnx_bytes
        ):
            raise SecurityError(
                f"ONNX size mismatch for {asset.onnx_filename}: expected {asset.expected_onnx_bytes}, got {size_bytes}"
            )

        if (
            asset.expected_onnx_sha256 is not None
            and sha256_hex != asset.expected_onnx_sha256.lower()
        ):
            raise SecurityError(
                f"SHA-256 integrity check failed for {asset.onnx_filename}"
            )

        if (
            asset.expected_onnx_md5 is not None
            and md5_hex != asset.expected_onnx_md5.lower()
        ):
            raise SecurityError(f"MD5 integrity check failed for {asset.onnx_filename}")

    @classmethod
    def verify_json_file(cls, json_path: Path, asset: VoiceModelAsset) -> None:
        """Verifies digest and strict schema of a downloaded .onnx.json configuration file."""
        if not json_path.exists():
            raise SecurityError(f"Missing JSON config file: {json_path.name}")

        _, md5_hex, size_bytes = cls.compute_digests(json_path)
        if size_bytes <= 2 or size_bytes > MAX_JSON_BYTES:
            raise SecurityError(
                f"Voice JSON config size out of safe bounds ({size_bytes} bytes)"
            )

        if (
            asset.expected_json_md5 is not None
            and md5_hex != asset.expected_json_md5.lower()
        ):
            raise SecurityError(f"MD5 integrity check failed for {asset.json_filename}")

        try:
            raw_text = json_path.read_text(encoding="utf-8")
            parsed = json.loads(raw_text)
        except Exception as e:
            raise SecurityError(
                f"Invalid JSON structure in {asset.json_filename}: {e}"
            ) from e

        if not isinstance(parsed, dict):
            raise SecurityError(f"Root of {asset.json_filename} must be a JSON object")

        audio_block = parsed.get("audio")
        phoneme_map = parsed.get("phoneme_id_map")
        inference_block = parsed.get("inference")

        if (
            not isinstance(audio_block, dict)
            or not isinstance(audio_block.get("sample_rate"), int)
            or not isinstance(phoneme_map, dict)
            or (inference_block is not None and not isinstance(inference_block, dict))
        ):
            raise SecurityError(
                f"Schema validation failed for voice config {asset.json_filename}"
            )

        # Ensure default inference parameters exist and normalize IPA phoneme keys to ASCII
        # escapes (\uXXXX) so piper_onnx's open(config_path) on Windows (cp1252) never fails.
        inf_dict = parsed.setdefault("inference", {})
        inf_dict.setdefault("length_scale", 1.0)
        inf_dict.setdefault("noise_scale", 0.667)
        inf_dict.setdefault("noise_w", 0.8)
        try:
            json_path.write_text(
                json.dumps(parsed, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def is_asset_installed(self, asset: VoiceModelAsset) -> bool:
        """Checks whether both .onnx and .onnx.json exist locally with valid sizes."""
        try:
            onnx_path = self._safe_path(asset.onnx_filename)
            json_path = self._safe_path(asset.json_filename)
            if not onnx_path.exists() or not json_path.exists():
                return False
            onnx_size = onnx_path.stat().st_size
            json_size = json_path.stat().st_size
            if onnx_size < MIN_ONNX_BYTES or onnx_size > MAX_ONNX_BYTES:
                return False
            if (
                asset.expected_onnx_bytes is not None
                and onnx_size != asset.expected_onnx_bytes
            ):
                return False
            if json_size <= 2 or json_size > MAX_JSON_BYTES:
                return False
            return True
        except Exception:
            return False

    def is_voice_installed(self, voice_id: str) -> bool:
        """Returns True if the voice is built-in (sapi5) or its neural asset is installed."""
        preset = get_voice_preset(voice_id)
        if preset.provider == "sapi5" or preset.model_asset is None:
            return True
        return self.is_asset_installed(preset.model_asset)

    def get_model_paths(self, voice_id: str) -> tuple[Path, Path] | None:
        """Returns (onnx_path, json_path) for an installed neural voice, or None."""
        preset = get_voice_preset(voice_id)
        if preset.model_asset is None:
            return None
        if not self.is_asset_installed(preset.model_asset):
            return None
        onnx_path = self._safe_path(preset.model_asset.onnx_filename)
        json_path = self._safe_path(preset.model_asset.json_filename)
        return onnx_path, json_path

    def _download_file_verified(
        self,
        url: str,
        dest_path: Path,
        max_bytes: int,
        progress_callback: Callable[[int, int], None] | None = None,
        timeout: float = 30.0,
    ) -> Path:
        """Streams a file over verified HTTPS to a temporary .part file with size enforcement."""
        self.validate_download_url(url)
        temp_path = dest_path.with_suffix(dest_path.suffix + ".part")
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"Jarvis-Voice-Downloader/{get_app_version()}"},
        )

        try:
            with (
                urllib.request.urlopen(
                    req, timeout=timeout, context=ssl_context
                ) as resp,
                open(temp_path, "wb") as out_file,
            ):
                final_url = resp.geturl()
                if final_url:
                    self.validate_download_url(final_url)

                total_size = int(resp.headers.get("Content-Length", 0))
                if total_size > max_bytes:
                    raise SecurityError(
                        f"Remote Content-Length ({total_size}) exceeds safety limit ({max_bytes})"
                    )

                downloaded = 0
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise SecurityError(
                            f"Download stream exceeded safety limit ({max_bytes} bytes)"
                        )
                    out_file.write(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_size)

            return temp_path
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

    def download_voice_model(
        self,
        voice_id: str,
        progress_callback: Callable[[int, int], None] | None = None,
        timeout: float = 30.0,
    ) -> tuple[Path, Path]:
        """Downloads and cryptographically verifies the neural model for voice_id."""
        preset = get_voice_preset(voice_id)
        asset = preset.model_asset
        if asset is None:
            raise ValueError(
                f"Voice '{voice_id}' is built-in and requires no download."
            )

        self.voices_dir.mkdir(parents=True, exist_ok=True)
        onnx_dest = self._safe_path(asset.onnx_filename)
        json_dest = self._safe_path(asset.json_filename)

        onnx_part: Path | None = None
        json_part: Path | None = None
        try:
            logger.info(
                f"Downloading voice config for '{voice_id}' ({asset.json_filename})..."
            )
            json_part = self._download_file_verified(
                url=asset.json_url,
                dest_path=json_dest,
                max_bytes=MAX_JSON_BYTES,
                progress_callback=None,
                timeout=timeout,
            )
            self.verify_json_file(json_part, asset)

            logger.info(
                f"Downloading voice model for '{voice_id}' ({asset.onnx_filename})..."
            )
            onnx_part = self._download_file_verified(
                url=asset.onnx_url,
                dest_path=onnx_dest,
                max_bytes=MAX_ONNX_BYTES,
                progress_callback=progress_callback,
                timeout=timeout,
            )
            self.verify_onnx_file(onnx_part, asset)

            os.replace(json_part, json_dest)
            os.replace(onnx_part, onnx_dest)
            logger.info(f"Voice model '{asset.model_key}' verified and installed.")
            return onnx_dest, json_dest
        except Exception:
            for part in (json_part, onnx_part):
                if part and part.exists():
                    try:
                        part.unlink()
                    except OSError:
                        pass
            raise

    def delete_voice_model(self, voice_id: str) -> int:
        """Deletes the downloaded files for voice_id and returns freed bytes."""
        preset = get_voice_preset(voice_id)
        if preset.model_asset is None:
            return 0
        return self._delete_asset_files(preset.model_asset)

    def _delete_asset_files(self, asset: VoiceModelAsset) -> int:
        freed_bytes = 0
        for fname in (asset.onnx_filename, asset.json_filename):
            target = self._safe_path(fname)
            if target.exists():
                try:
                    size = target.stat().st_size
                    target.unlink()
                    freed_bytes += size
                except OSError as e:
                    logger.warning(f"Could not delete voice file {target}: {e}")
        return freed_bytes

    def get_unused_downloaded_stats(self, active_voice_id: str) -> tuple[int, int]:
        """Returns (unused_packages_count, unused_bytes) for downloaded models not used by active_voice_id."""
        active_preset = get_voice_preset(active_voice_id)
        active_model_key = (
            active_preset.model_asset.model_key if active_preset.model_asset else None
        )

        unused_count = 0
        unused_bytes = 0
        for model_key, asset in MODEL_ASSETS.items():
            if model_key == active_model_key:
                continue
            onnx_path = self._safe_path(asset.onnx_filename)
            json_path = self._safe_path(asset.json_filename)
            pkg_bytes = 0
            if onnx_path.exists():
                pkg_bytes += onnx_path.stat().st_size
            if json_path.exists():
                pkg_bytes += json_path.stat().st_size
            if pkg_bytes > 0:
                unused_count += 1
                unused_bytes += pkg_bytes

        return unused_count, unused_bytes

    def cleanup_unused_voices(self, active_voice_id: str) -> tuple[int, int]:
        """Deletes all downloaded neural voice models except the one required by active_voice_id.

        Never touches the built-in Windows SAPI5 voice.
        Returns (removed_packages_count, freed_bytes).
        """
        active_preset = get_voice_preset(active_voice_id)
        active_model_key = (
            active_preset.model_asset.model_key if active_preset.model_asset else None
        )

        removed_count = 0
        freed_bytes = 0
        for model_key, asset in MODEL_ASSETS.items():
            if model_key == active_model_key:
                continue
            deleted_size = self._delete_asset_files(asset)
            if deleted_size > 0:
                removed_count += 1
                freed_bytes += deleted_size

        # Also clean up any leftover temporary .part files in voices_dir
        try:
            for part_file in self.voices_dir.glob("*.part"):
                if part_file.is_file():
                    try:
                        freed_bytes += part_file.stat().st_size
                        part_file.unlink()
                    except OSError:
                        pass
        except OSError:
            pass

        return removed_count, freed_bytes
