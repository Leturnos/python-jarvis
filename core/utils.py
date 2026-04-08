import os
import sys
import winreg
import win32com.client
from pathlib import Path
from PIL import Image, ImageDraw
from core.logger_config import logger

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
    project_dir = str(Path(__file__).parent.parent.absolute())
    resources_dir = get_resources_dir()
    shortcut_path = str(resources_dir / "Jarvis.lnk")
    icon_path = generate_icon_if_needed()
    
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        
        if not enable:
            try:
                winreg.DeleteValue(key, app_name)
                winreg.CloseKey(key)
                logger.info("Removed Jarvis from Startup Registry.")
                return "Jarvis removed from Startup."
            except FileNotFoundError:
                winreg.CloseKey(key)
                return "Jarvis was not in Startup."
        
        # Enable: Create/Update the shortcut
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        
        # cmd.exe is the engine to run the python environment
        shortcut.Targetpath = "cmd.exe"
        shortcut.Arguments = f'/c "cd /d {project_dir} && uv run main.py"'
        shortcut.WorkingDirectory = project_dir
        shortcut.WindowStyle = 7 # Minimized
        shortcut.IconLocation = f"{icon_path},0"
        shortcut.Description = "Jarvis AI Assistant"
        shortcut.save()

        # Set the Registry to point to the SHORTCUT in the resources folder
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{shortcut_path}"')
        winreg.CloseKey(key)
        
        logger.info(f"Jarvis added to Startup Registry via shortcut: {shortcut_path}")
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
