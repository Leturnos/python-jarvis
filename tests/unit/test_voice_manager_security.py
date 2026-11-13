import hashlib
import json
from pathlib import Path

import pytest

from core.audio.voice_catalog import MODEL_ASSETS, VoiceModelAsset
from core.audio.voice_manager import MIN_ONNX_BYTES, VoiceManager
from core.shared.errors import SecurityError


def test_validate_download_url_enforces_https_and_allowlist():
    VoiceManager.validate_download_url(
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/model.onnx"
    )
    # Official Hugging Face AWS/Xet CDN redirect domains must be allowed over HTTPS
    VoiceManager.validate_download_url(
        "https://us.aws.cdn.hf.co/xet-bridge-us/622625/model.onnx"
    )
    VoiceManager.validate_download_url(
        "https://cdn-lfs.huggingface.co/repos/model.onnx"
    )

    with pytest.raises(SecurityError, match="Insecure voice download protocol"):
        VoiceManager.validate_download_url(
            "http://huggingface.co/rhasspy/piper-voices/model.onnx"
        )
    with pytest.raises(SecurityError, match="Insecure voice download protocol"):
        VoiceManager.validate_download_url(
            "http://us.aws.cdn.hf.co/xet-bridge-us/model.onnx"
        )

    for untrusted in (
        "https://evil.example.com/model.onnx",
        "https://evil-hf.co/model.onnx",
        "https://huggingface.co.evil.com/model.onnx",
    ):
        with pytest.raises(SecurityError, match="Untrusted voice download host"):
            VoiceManager.validate_download_url(untrusted)


def test_format_user_error_returns_friendly_ptbr_messages():
    msg_host = VoiceManager.format_user_error(
        SecurityError("Untrusted voice download host blocked: 'evil.com'")
    )
    assert "bloqueado por segurança" in msg_host.lower()
    assert "evil.com" not in msg_host

    msg_hash = VoiceManager.format_user_error(
        SecurityError("SHA-256 integrity check failed for model.onnx")
    )
    assert "verificação de integridade" in msg_hash.lower()

    msg_net = VoiceManager.format_user_error(TimeoutError("timed out"))
    assert "conectar ao servidor" in msg_net.lower()


def test_safe_path_blocks_traversal(tmp_path: Path):
    mgr = VoiceManager(voices_dir=tmp_path)
    valid = mgr._safe_path("pt_BR-faber-medium.onnx")
    assert valid.parent == tmp_path.resolve()

    for bad_name in ("../secret.onnx", "sub/model.onnx", r"sub\model.onnx", ""):
        with pytest.raises(SecurityError):
            mgr._safe_path(bad_name)


def test_verify_onnx_and_json_integrity_rejects_tampered_files(tmp_path: Path):
    payload = b"x" * (MIN_ONNX_BYTES + 128)
    good_sha256 = hashlib.sha256(payload).hexdigest()
    good_md5 = hashlib.md5(payload).hexdigest()

    onnx_file = tmp_path / "test.onnx"
    onnx_file.write_bytes(payload)

    valid_json_content = json.dumps(
        {
            "audio": {"sample_rate": 22050},
            "phoneme_id_map": {"^": [1], "$": [2], "_": [0]},
            "inference": {"length_scale": 1.0, "noise_scale": 0.667, "noise_w": 0.8},
        }
    ).encode("utf-8")
    json_md5 = hashlib.md5(valid_json_content).hexdigest()
    json_file = tmp_path / "test.onnx.json"
    json_file.write_bytes(valid_json_content)

    asset = VoiceModelAsset(
        model_key="test",
        onnx_filename="test.onnx",
        json_filename="test.onnx.json",
        onnx_url="https://huggingface.co/test.onnx",
        json_url="https://huggingface.co/test.onnx.json",
        approx_size_mb=1.2,
        expected_onnx_bytes=len(payload),
        expected_onnx_sha256=good_sha256,
        expected_onnx_md5=good_md5,
        expected_json_md5=json_md5,
    )

    VoiceManager.verify_onnx_file(onnx_file, asset)
    VoiceManager.verify_json_file(json_file, asset)

    # Tamper 1 byte in ONNX
    onnx_file.write_bytes(b"y" + payload[1:])
    with pytest.raises(SecurityError, match="SHA-256 integrity check failed"):
        VoiceManager.verify_onnx_file(onnx_file, asset)

    # Invalid JSON schema (missing phoneme_id_map)
    bad_json = tmp_path / "bad.onnx.json"
    bad_json.write_text('{"audio": {"sample_rate": 22050}}', encoding="utf-8")
    asset_no_md5 = VoiceModelAsset(
        model_key="test2",
        onnx_filename="test.onnx",
        json_filename="bad.onnx.json",
        onnx_url="https://huggingface.co/test.onnx",
        json_url="https://huggingface.co/bad.onnx.json",
        approx_size_mb=1.2,
    )
    with pytest.raises(SecurityError, match="Schema validation failed"):
        VoiceManager.verify_json_file(bad_json, asset_no_md5)


def test_cleanup_unused_voices_preserves_only_active_voice(tmp_path: Path):
    mgr = VoiceManager(voices_dir=tmp_path)

    # Simulate downloaded files for 'jarvis_mk3' and 'faber' (now completely independent)
    jarvis_asset = MODEL_ASSETS["jarvis_mk3"]
    faber_asset = MODEL_ASSETS["faber"]

    (tmp_path / jarvis_asset.onnx_filename).write_bytes(b"a" * (MIN_ONNX_BYTES + 10))
    (tmp_path / jarvis_asset.json_filename).write_bytes(b'{"audio": {}}')
    (tmp_path / faber_asset.onnx_filename).write_bytes(b"b" * 4096)
    (tmp_path / faber_asset.json_filename).write_bytes(b"{}")

    # Downloading jarvis_mk3 does NOT mark piper_faber as installed
    assert mgr.is_voice_installed("piper_faber") is False

    unused_count, unused_bytes = mgr.get_unused_downloaded_stats("jarvis_mk3")
    assert unused_count == 1
    assert unused_bytes == 4098

    removed_count, freed_bytes = mgr.cleanup_unused_voices("jarvis_mk3")
    assert removed_count == 1
    assert freed_bytes == 4098

    # 'jarvis_mk3' files remain untouched; 'faber' files are removed
    assert (tmp_path / jarvis_asset.onnx_filename).exists()
    assert not (tmp_path / faber_asset.onnx_filename).exists()

    # When switching to Windows native voice ('sapi5_default'), 'jarvis_mk3' becomes unused
    removed_count_2, _ = mgr.cleanup_unused_voices("sapi5_default")
    assert removed_count_2 == 1
    assert not (tmp_path / jarvis_asset.onnx_filename).exists()
    assert mgr.is_voice_installed("sapi5_default") is True
