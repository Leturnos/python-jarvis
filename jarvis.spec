# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for Jarvis AI Assistant.

Builds a portable one-folder bundle (dist/Jarvis/) with no black console window
and all essential neural net / UI runtime dependencies.
"""

import glob
import os
from pathlib import Path

block_cipher = None

from PyInstaller.utils.hooks import collect_data_files

# Base datas required at runtime
datas = [
    ('plugins/*.yaml', 'plugins'),
    ('resources/*', 'resources'),
    ('config.yaml', '.'),
]

# Collect essential package data files to prevent FileNotFoundError in frozen binaries
package_datas = ['litellm', 'openwakeword', 'faster_whisper', 'qdarktheme', 'tiktoken', 'tiktoken_ext']
for pkg in package_datas:
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

# Include onnx models if present; fallback to copying the models dir if none found yet
if glob.glob('models/*.onnx'):
    datas.append(('models/*.onnx', 'models'))
else:
    datas.append(('models', 'models'))

hidden_imports = [
    'litellm',
    'litellm.providers',
    'litellm.litellm_core_utils',
    'litellm.llms',
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    'faster_whisper',
    'openwakeword',
    'plyer.platforms.win.notification',
    'win32timezone',
    'qdarktheme',
    'qfluentwidgets',
    'ctranslate2',
    'onnxruntime',
    'numpy',
    'PIL',
    'keyring.backends.Windows',
    'psutil',
    'pyautogui',
    'pyqtdarktheme',
    'keyboard',
    'pyaudio',
    'pyperclip',
    'pythoncom',
    'win32gui',
    'win32con',
    'win32api',
    'win32process',
    'win32com',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Jarvis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Jarvis',
)
