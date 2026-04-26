import os
import sys
import winreg
import win32com.client
import re
from pathlib import Path
from PIL import Image, ImageDraw
from core.logger_config import logger

import time
import functools

def time_it(func):
    """Decorator to measure and log the execution time of a function."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        duration = end_time - start_time
        logger.info(f"Performance: {func.__name__} took {duration:.4f} seconds")
        return result
    return wrapper

def normalize_text(text):
    """Normalizes text for matching: lowercase, remove punctuation, spaces to underscores."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip().replace(" ", "_")

def get_resources_dir():
    """Returns and ensures the resources directory exists."""
    project_dir = Path(__file__).parent.parent.absolute()
    resources_dir = project_dir / "resources"
    resources_dir.mkdir(exist_ok=True)
    return resources_dir

def generate_icon_if_needed():
    """Generates the icon.ico file if it doesn't exist in resources."""
    resources_dir = get_resources_dir()
    icon_path = resources_dir / "icon.ico"
    
    if not icon_path.exists():
        width, height = 256, 256
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        color1 = (0, 0, 255)   # Blue
        color2 = (0, 255, 255) # Cyan
        dc.ellipse([16, 16, width-16, height-16], fill=color1, outline=color2, width=8)
        dc.ellipse([width//2-40, height//2-40, width//2+40, height//2+40], fill=color2)
        image.save(str(icon_path), format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        logger.info(f"Generated missing icon at {icon_path}")
    
    return str(icon_path)

def manage_autostart(enable=True):
    """Adds or removes Jarvis from Windows Startup using a Shortcut in the Registry."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "JarvisAI"
    project_dir = Path(__file__).parent.parent.absolute()
    resources_dir = get_resources_dir()
    shortcut_path = str(resources_dir / "Jarvis.lnk")
    vbs_path = resources_dir / "launcher.vbs"
    icon_path = generate_icon_if_needed()
    
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        
        if not enable:
            if vbs_path.exists():
                vbs_path.unlink()
            try:
                winreg.DeleteValue(key, app_name)
                winreg.CloseKey(key)
                logger.info("Removed Jarvis from Startup Registry.")
                return "Jarvis removed from Startup."
            except FileNotFoundError:
                winreg.CloseKey(key)
                return "Jarvis was not in Startup."
        
        # Enable: Create the VBS launcher to run uv silently
        vbs_content = f"""Set objShell = WScript.CreateObject("WScript.Shell")
objShell.CurrentDirectory = "{str(project_dir)}"
objShell.Run "uv run main.py --hidden", 0, False
"""
        with open(vbs_path, "w") as f:
            f.write(vbs_content)

        # Enable: Create/Update the shortcut
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        
        # wscript.exe runs the VBS launcher without a console
        shortcut.Targetpath = "wscript.exe"
        shortcut.Arguments = f'"{str(vbs_path)}"'
        shortcut.WorkingDirectory = str(project_dir)
        shortcut.WindowStyle = 7 # Minimized
        shortcut.IconLocation = f"{icon_path},0"
        shortcut.Description = "Jarvis AI Assistant"
        shortcut.save()

        # Set the Registry to point to the SHORTCUT in the resources folder
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{shortcut_path}"')
        winreg.CloseKey(key)
        
        logger.info(f"Jarvis added to Startup Registry via VBS launcher: {vbs_path}")
        return "Jarvis successfully added to Startup! (Check Settings -> Apps -> Startup)"
        
    except Exception as e:
        logger.error(f"Failed to manage autostart registry: {e}")
        return f"Error: {e}"

def is_autostart_enabled_check():
    """Checks if the registry key exists."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "JarvisAI"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, app_name)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False
