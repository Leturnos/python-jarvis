import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SPEC_FILE = ROOT_DIR / "jarvis.spec"
BUILD_SCRIPT = ROOT_DIR / "scripts" / "build_exe.py"


def test_spec_file_exists_and_is_valid_ast():
    assert SPEC_FILE.exists(), f"jarvis.spec does not exist at {SPEC_FILE}"
    content = SPEC_FILE.read_text(encoding="utf-8")
    tree = ast.parse(content, filename="jarvis.spec")
    assert isinstance(tree, ast.Module)


def test_spec_file_configuration():
    assert SPEC_FILE.exists()
    content = SPEC_FILE.read_text(encoding="utf-8")

    # Verify essential strings and flags in spec
    assert "console=False" in content, "Spec must specify console=False"
    assert "upx=False" in content, (
        "Spec must disable UPX (upx=False) to avoid DLL corruption"
    )
    assert "name='Jarvis'" in content or 'name="Jarvis"' in content, (
        "Spec must name the output 'Jarvis'"
    )

    # Verify datas inclusions
    assert "models" in content, "Spec must include models in datas"
    assert "plugins" in content, "Spec must include plugins in datas"
    assert "resources" in content, "Spec must include resources in datas"
    assert "config.yaml" in content, "Spec must include config.yaml in datas"

    # Verify essential hiddenimports
    essential_hidden_imports = [
        "litellm",
        "faster_whisper",
        "openwakeword",
        "plyer.platforms.win.notification",
        "win32timezone",
        "qdarktheme",
        "qfluentwidgets",
        "ctranslate2",
        "onnxruntime",
        "numpy",
        "PIL",
        "keyring.backends.Windows",
        "psutil",
        "pyautogui",
    ]
    for imp in essential_hidden_imports:
        assert imp in content, f"Spec missing required hiddenimport: {imp}"


def test_build_script_exists_and_is_valid_ast():
    assert BUILD_SCRIPT.exists(), (
        f"scripts/build_exe.py does not exist at {BUILD_SCRIPT}"
    )
    content = BUILD_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(content, filename="scripts/build_exe.py")
    assert isinstance(tree, ast.Module)

    # Verify required functions are defined in AST
    defined_funcs = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "verify_prerequisites" in defined_funcs
    assert "generate_icon_if_needed" in defined_funcs
    assert "build_bundle" in defined_funcs
    assert "main" in defined_funcs


def test_verify_prerequisites_missing_models(tmp_path):
    sys.path.insert(0, str(ROOT_DIR))
    try:
        from scripts.build_exe import verify_prerequisites

        fake_models_dir = tmp_path / "models"
        fake_models_dir.mkdir()
        fake_icon = tmp_path / "resources" / "icon.ico"
        fake_icon.parent.mkdir(parents=True)
        fake_icon.write_bytes(b"dummy")

        with (
            patch("scripts.build_exe.MODELS_DIR", fake_models_dir),
            patch("scripts.build_exe.ICON_FILE", fake_icon),
        ):
            # No .onnx files in models dir
            assert verify_prerequisites() is False
    finally:
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))


def test_verify_prerequisites_success(tmp_path):
    sys.path.insert(0, str(ROOT_DIR))
    try:
        from scripts.build_exe import verify_prerequisites

        fake_models_dir = tmp_path / "models"
        fake_models_dir.mkdir()
        (fake_models_dir / "hey_jarvis.onnx").write_bytes(b"dummy model")
        fake_spec = tmp_path / "jarvis.spec"
        fake_spec.write_text("spec content", encoding="utf-8")

        with (
            patch("scripts.build_exe.MODELS_DIR", fake_models_dir),
            patch("scripts.build_exe.SPEC_FILE", fake_spec),
        ):
            assert verify_prerequisites() is True
    finally:
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))


def test_generate_icon_if_needed(tmp_path):
    sys.path.insert(0, str(ROOT_DIR))
    try:
        from scripts.build_exe import generate_icon_if_needed

        target_icon = tmp_path / "resources" / "test_icon.ico"
        assert not target_icon.exists()

        result_path = generate_icon_if_needed(target_icon)
        assert target_icon.exists()
        assert result_path == target_icon
        assert target_icon.stat().st_size > 0

        # Calling again should return existing icon
        cached_result = generate_icon_if_needed(target_icon)
        assert cached_result == target_icon
    finally:
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))


def test_directory_size_and_formatting(tmp_path):
    sys.path.insert(0, str(ROOT_DIR))
    try:
        from scripts.build_exe import format_bytes, get_directory_size

        sub_dir = tmp_path / "test_dir"
        sub_dir.mkdir()
        f1 = sub_dir / "file1.bin"
        f1.write_bytes(b"a" * 1024)
        f2 = sub_dir / "file2.bin"
        f2.write_bytes(b"b" * 2048)

        total = get_directory_size(sub_dir)
        assert total == 3072

        formatted = format_bytes(total)
        assert "3.00 KB" in formatted
        assert "MB" in format_bytes(1024 * 1024 * 5)
    finally:
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))


def test_build_bundle_invokes_subprocess():
    sys.path.insert(0, str(ROOT_DIR))
    try:
        from scripts.build_exe import build_bundle

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            success = build_bundle()
            assert success is True
            assert mock_run.called
            args, kwargs = mock_run.call_args
            cmd = args[0]
            assert "--noconfirm" in cmd
            assert "--clean" in cmd
            assert "jarvis.spec" in " ".join(cmd)
    finally:
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))


def test_main_execution_flow(tmp_path):
    sys.path.insert(0, str(ROOT_DIR))
    try:
        from scripts.build_exe import main

        fake_exe = tmp_path / "dist" / "Jarvis" / "Jarvis.exe"
        fake_exe.parent.mkdir(parents=True)
        fake_exe.write_bytes(b"exe")

        with (
            patch("scripts.build_exe.verify_prerequisites", return_value=True),
            patch(
                "scripts.build_exe.generate_icon_if_needed",
                return_value=tmp_path / "icon.ico",
            ),
            patch("scripts.build_exe.build_bundle", return_value=True),
            patch("scripts.build_exe.EXE_FILE", fake_exe),
            patch("scripts.build_exe.DIST_DIR", fake_exe.parent),
            patch("scripts.build_exe.print_report") as mock_report,
        ):
            ret = main()
            assert ret == 0
            mock_report.assert_called_once()
    finally:
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))
