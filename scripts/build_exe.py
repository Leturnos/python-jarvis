"""Automated build script for Jarvis PyInstaller one-folder bundle."""

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("JarvisBuild")

ROOT_DIR = Path(__file__).resolve().parent.parent
SPEC_FILE = ROOT_DIR / "jarvis.spec"
MODELS_DIR = ROOT_DIR / "models"
RESOURCES_DIR = ROOT_DIR / "resources"
ICON_FILE = RESOURCES_DIR / "icon.ico"
DIST_DIR = ROOT_DIR / "dist" / "Jarvis"
EXE_FILE = DIST_DIR / "Jarvis.exe"


def generate_icon_if_needed(icon_path: Path | None = None) -> Path:
    """Ensure an application icon exists, creating a default one if missing."""
    target = icon_path or ICON_FILE
    if target.exists():
        logger.info(f"Icon already exists at {target}")
        return target

    logger.info(f"Generating default application icon at {target}...")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw

        # Create a 64x64 blue icon with an inner circle
        img = Image.new("RGBA", (64, 64), color=(20, 24, 35, 255))
        draw = ImageDraw.Draw(img)
        draw.ellipse(
            (8, 8, 56, 56),
            fill=(0, 168, 255, 255),
            outline=(255, 255, 255, 255),
            width=2,
        )
        img.save(str(target), format="ICO")
    except Exception as exc:
        logger.warning(
            f"Failed to generate icon using PIL ({exc}), creating minimal ICO fallback"
        )
        target.write_bytes(
            b"\x00\x00\x01\x00\x01\x00\x01\x01\x00\x00\x01\x00 \x00(\x00\x00\x00\x16\x00\x00\x00"
        )

    logger.info(f"Icon successfully generated at {target}")
    return target


def ensure_default_wakeword_model(models_dir: Path | None = None) -> Path | None:
    """Ensure at least one wakeword model exists in models/, copying 'hey_jarvis' as default if needed."""
    target_dir = models_dir or MODELS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    existing = list(target_dir.glob("*.onnx"))
    if existing:
        logger.info(
            f"Found existing wakeword model(s) in {target_dir}: {[f.name for f in existing]}"
        )
        return existing[0]

    logger.info(
        f"No .onnx models found in {target_dir}. Looking for default 'hey_jarvis' model from openwakeword..."
    )
    try:
        import openwakeword

        pretrained = openwakeword.get_pretrained_model_paths()
        jarvis_model = None
        for p in pretrained:
            if "hey_jarvis" in Path(p).name.lower():
                jarvis_model = Path(p)
                break

        if jarvis_model and jarvis_model.exists():
            dest = target_dir / jarvis_model.name
            shutil.copy2(jarvis_model, dest)
            logger.info(f"Default wakeword model successfully copied to {dest}")
            return dest
    except Exception as exc:
        logger.warning(f"Could not auto-copy default hey_jarvis model: {exc}")

    return None


def verify_prerequisites() -> bool:
    """Verify that all prerequisites for building the executable are met."""
    logger.info("Verifying build prerequisites...")

    if not SPEC_FILE.exists():
        logger.error(f"PyInstaller spec file not found: {SPEC_FILE}")
        return False

    # Ensure default 'hey_jarvis' model is available if models/ is empty
    ensure_default_wakeword_model(MODELS_DIR)

    # Check for presence of at least one .onnx model in models/
    onnx_models = list(MODELS_DIR.glob("*.onnx"))
    if not onnx_models:
        logger.error(
            f"No .onnx wakeword models found in {MODELS_DIR}. "
            "Please download or provide at least one model before building."
        )
        return False

    logger.info(f"Found {len(onnx_models)} .onnx model(s) in {MODELS_DIR}")
    return True


def get_directory_size(path: Path) -> int:
    """Calculate the total size in bytes of all files in a directory."""
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def format_bytes(size: int) -> str:
    """Format bytes into a human-readable string."""
    size_float = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if size_float < 1024.0 or unit == "GB":
            return f"{size_float:.2f} {unit}"
        size_float /= 1024.0
    return f"{size_float:.2f} GB"


def build_bundle(spec_file: Path | None = None) -> bool:
    """Run PyInstaller to create the one-folder bundle."""
    target_spec = spec_file or SPEC_FILE
    logger.info(f"Building Jarvis bundle using {target_spec}...")

    venv_pyinstaller = Path(sys.executable).parent / (
        "pyinstaller.exe" if sys.platform == "win32" else "pyinstaller"
    )
    if venv_pyinstaller.exists():
        cmd = [str(venv_pyinstaller), str(target_spec.name), "--noconfirm", "--clean"]
    elif shutil.which("pyinstaller"):
        cmd = [
            shutil.which("pyinstaller"),  # type: ignore[list-item]
            str(target_spec.name),
            "--noconfirm",
            "--clean",
        ]
    else:
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            str(target_spec.name),
            "--noconfirm",
            "--clean",
        ]

    logger.info(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if result.returncode != 0:
        logger.error(f"PyInstaller failed with return code {result.returncode}")
        return False

    return True


def print_report(dist_dir: Path, exe_file: Path) -> None:
    """Print build completion report and usage instructions."""
    total_size = get_directory_size(dist_dir)
    formatted_size = format_bytes(total_size)

    report = f"""
======================================================================
                   JARVIS BUILD COMPLETE
======================================================================
 Executable: {exe_file}
 Directory:  {dist_dir}
 Total Size: {formatted_size}
 Status:     READY FOR PORTABLE DISTRIBUTION
======================================================================
 Instructions:
 1. Copy the entire '{dist_dir.name}' folder to any destination on Windows.
 2. Run '{exe_file.name}' to start the Jarvis Assistant.
 3. Ensure your API keys are configured in '{dist_dir / "config.yaml"}' or .env.
======================================================================
"""
    print(report)


def copy_user_facing_assets(dist_dir: Path | None = None) -> None:
    """Copy config.yaml, models, plugins and resources to the bundle root for user accessibility."""
    target = dist_dir or DIST_DIR
    if not target.exists():
        return

    logger.info(f"Copying user-facing assets to bundle root at {target}...")

    # 1. config.yaml
    cfg_src = ROOT_DIR / "config.yaml"
    if cfg_src.exists():
        shutil.copy2(cfg_src, target / "config.yaml")

    # 2. models/
    models_target = target / "models"
    models_target.mkdir(parents=True, exist_ok=True)
    if MODELS_DIR.exists():
        for f in MODELS_DIR.glob("*.onnx"):
            shutil.copy2(f, models_target / f.name)

    # 3. plugins/
    plugins_src = ROOT_DIR / "plugins"
    plugins_target = target / "plugins"
    plugins_target.mkdir(parents=True, exist_ok=True)
    if plugins_src.exists():
        for f in plugins_src.glob("*.*"):
            shutil.copy2(f, plugins_target / f.name)

    # 4. resources/
    resources_src = ROOT_DIR / "resources"
    resources_target = target / "resources"
    resources_target.mkdir(parents=True, exist_ok=True)
    if resources_src.exists():
        for f in resources_src.glob("*.*"):
            shutil.copy2(f, resources_target / f.name)

    logger.info("User-facing assets successfully copied to bundle root.")


def main() -> int:
    """Entry point for the build script."""
    generate_icon_if_needed()

    if not verify_prerequisites():
        return 1

    if not build_bundle():
        return 1

    if not EXE_FILE.exists():
        logger.error(f"Build succeeded but {EXE_FILE} was not found!")
        return 1

    copy_user_facing_assets(DIST_DIR)

    print_report(DIST_DIR, EXE_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
