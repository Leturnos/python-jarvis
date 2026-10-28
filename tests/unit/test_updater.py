import json
import zipfile
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from core.infra.updater import UpdateManager, normalize_repo, parse_version
from core.shared.errors import SecurityError


def test_normalize_repo():
    assert (
        normalize_repo("https://github.com/Leturnos/python-jarvis")
        == "Leturnos/python-jarvis"
    )
    assert (
        normalize_repo("https://github.com/Leturnos/python-jarvis.git")
        == "Leturnos/python-jarvis"
    )
    assert (
        normalize_repo("http://github.com/Leturnos/python-jarvis/")
        == "Leturnos/python-jarvis"
    )
    assert normalize_repo("Leturnos/python-jarvis") == "Leturnos/python-jarvis"
    assert normalize_repo("  Leturnos/python-jarvis  ") == "Leturnos/python-jarvis"


def test_parse_version():
    assert parse_version("0.2.1") == (0, 2, 1)
    assert parse_version("v0.2.1") == (0, 2, 1)
    assert parse_version("v1.0.0") == (1, 0, 0)
    assert parse_version("v0.10.2") == (0, 10, 2)
    assert parse_version("v0.2.1") < parse_version("v0.3.0")
    assert parse_version("v0.3.0") > parse_version("0.2.9")
    assert parse_version("invalid") == (0, 0, 0)


def test_check_for_updates_found():
    updater = UpdateManager(current_version="0.2.1", repo="Leturnos/python-jarvis")

    mock_response = MagicMock()
    mock_payload = {
        "tag_name": "v0.3.0",
        "name": "Jarvis 0.3.0 Release",
        "body": "Novas funcionalidades e correções.",
        "html_url": "https://github.com/Leturnos/python-jarvis/releases/tag/v0.3.0",
        "assets": [
            {
                "name": "Jarvis-v0.3.0-windows-x64.zip",
                "browser_download_url": "https://github.com/Leturnos/python-jarvis/releases/download/v0.3.0/Jarvis-v0.3.0-windows-x64.zip",
                "size": 52428800,
            }
        ],
    }
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        info = updater.check_for_updates()

    assert info is not None
    assert info.version == "v0.3.0"
    assert info.title == "Jarvis 0.3.0 Release"
    assert info.body == "Novas funcionalidades e correções."
    assert info.has_update is True
    assert (
        info.download_url
        == "https://github.com/Leturnos/python-jarvis/releases/download/v0.3.0/Jarvis-v0.3.0-windows-x64.zip"
    )
    assert info.asset_size == 52428800


def test_check_for_updates_no_newer_version():
    updater = UpdateManager(current_version="v0.3.0", repo="Leturnos/python-jarvis")

    mock_response = MagicMock()
    mock_payload = {
        "tag_name": "v0.3.0",
        "name": "Jarvis 0.3.0 Release",
        "body": "No updates",
        "html_url": "https://github.com/Leturnos/python-jarvis/releases/tag/v0.3.0",
        "assets": [
            {
                "name": "Jarvis-v0.3.0-windows-x64.zip",
                "browser_download_url": "https://example.com/asset.zip",
                "size": 1000,
            }
        ],
    }
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        info = updater.check_for_updates()

    assert info is not None
    assert info.version == "v0.3.0"
    assert info.has_update is False


def test_check_for_updates_network_failure():
    updater = UpdateManager(current_version="0.2.1", repo="Leturnos/python-jarvis")

    with patch("urllib.request.urlopen", side_effect=URLError("Connection refused")):
        info = updater.check_for_updates()

    assert info is None


def test_download_update(tmp_path):
    updater = UpdateManager(current_version="0.2.1", temp_dir=tmp_path)

    fake_data = b"ZIP_ARCHIVE_MOCK_DATA" * 100
    mock_response = MagicMock()
    mock_response.headers = {"Content-Length": str(len(fake_data))}
    # Simulate chunks
    mock_response.read.side_effect = [fake_data[:100], fake_data[100:], b""]
    mock_response.__enter__.return_value = mock_response

    progress_records = []

    def on_progress(downloaded: int, total: int):
        progress_records.append((downloaded, total))

    with patch("urllib.request.urlopen", return_value=mock_response):
        dest_zip = updater.download_asset(
            "https://example.com/mock.zip", progress_callback=on_progress
        )

    assert dest_zip.exists()
    assert dest_zip.read_bytes() == fake_data
    assert len(progress_records) > 0
    assert progress_records[-1] == (len(fake_data), len(fake_data))


def test_extract_and_prepare_update(tmp_path):
    updater = UpdateManager(current_version="0.2.1", temp_dir=tmp_path)

    # Create dummy zip with nested Jarvis directory
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Jarvis/Jarvis.exe", "fake exe binary")
        zf.writestr("Jarvis/resources/icon.ico", "fake icon")

    extracted_dir = updater.extract_archive(zip_path)
    assert extracted_dir.exists()
    assert (extracted_dir / "Jarvis.exe").exists()
    assert (extracted_dir / "resources" / "icon.ico").exists()


def test_extract_archive_blocks_zip_slip(tmp_path):
    updater = UpdateManager(current_version="0.2.1", temp_dir=tmp_path)
    zip_path = tmp_path / "malicious.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../malicious.exe", "evil content")

    with pytest.raises(SecurityError, match="Zip traversal detected"):
        updater.extract_archive(zip_path)


def test_generate_updater_script(tmp_path):
    updater = UpdateManager(current_version="0.2.1", temp_dir=tmp_path)
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "app"
    exe_path = dest_dir / "Jarvis.exe"

    source_dir.mkdir()
    dest_dir.mkdir()
    exe_path.touch()

    bat_path = updater.generate_batch_script(
        pid=1234,
        source_dir=source_dir,
        dest_dir=dest_dir,
        exe_path=exe_path,
    )

    assert bat_path.exists()
    content = bat_path.read_text(encoding="utf-8")
    assert "PID alvo: 1234" in content
    assert "robocopy" in content
    assert str(source_dir) in content
    assert str(dest_dir) in content
    assert str(exe_path) in content
    assert "/XD data logs" in content


def test_generate_updater_script_hardening(tmp_path):
    updater = UpdateManager(current_version="0.2.1", temp_dir=tmp_path)
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "app"
    exe_path = dest_dir / "Jarvis.exe"

    source_dir.mkdir()
    dest_dir.mkdir()
    exe_path.touch()

    bat_path = updater.generate_batch_script(
        pid=5678,
        source_dir=source_dir,
        dest_dir=dest_dir,
        exe_path=exe_path,
    )

    content = bat_path.read_text(encoding="utf-8")
    assert "PID alvo: 5678" in content
    assert "/R:5 /W:1" in content
    assert "LOG_FILE=" in content
    assert 'start "" /D' in content
    assert "tasklist" not in content  # Avoids WMI/RPC hanging on Windows


def test_apply_update_and_restart_with_custom_exit_callback(tmp_path):
    updater = UpdateManager(current_version="0.2.1", temp_dir=tmp_path)
    source_dir = tmp_path / "extracted_dir"
    source_dir.mkdir()
    mock_exit = MagicMock()

    with patch("subprocess.Popen") as mock_popen:
        updater.apply_update_and_restart(
            source_dir=source_dir,
            dest_dir=tmp_path / "app",
            exe_path=tmp_path / "app" / "Jarvis.exe",
            exit_callback=mock_exit,
        )

        mock_popen.assert_called_once()
        cmd_args = mock_popen.call_args[0][0]
        assert "cmd" in cmd_args[0].lower()
        assert "/c" in cmd_args[1]
        assert "updater.bat" in cmd_args[2]
        kwargs = mock_popen.call_args[1]
        assert kwargs.get("creationflags") & 0x08000000  # CREATE_NO_WINDOW
        assert kwargs.get("stdin") is not None  # DEVNULL
        mock_exit.assert_called_once()


def test_apply_update_and_restart_defaults_to_os_exit(tmp_path):
    updater = UpdateManager(current_version="0.2.1", temp_dir=tmp_path)
    source_dir = tmp_path / "extracted_dir"
    source_dir.mkdir()

    with patch("subprocess.Popen") as mock_popen, patch("os._exit") as mock_exit:
        updater.apply_update_and_restart(
            source_dir=source_dir,
            dest_dir=tmp_path / "app",
            exe_path=tmp_path / "app" / "Jarvis.exe",
        )

        mock_popen.assert_called_once()
        mock_exit.assert_called_once_with(0)
