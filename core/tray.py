import pystray
from PIL import Image, ImageDraw
import threading
import ctypes
import win32gui
import win32con
import os
from core.logger_config import logger
from core.utils import manage_autostart, is_autostart_enabled_check

class JarvisTray:
    def __init__(self, on_stop_callback):
        self.on_stop_callback = on_stop_callback
        self.icon = None
        self.icon_thread = None
        self.console_window = self._get_console_window()
        self.console_visible = True

    def _get_console_window(self):
        """Returns the handle of the current console window."""
        return ctypes.windll.kernel32.GetConsoleWindow()

    def create_image(self, width=64, height=64, color1="blue", color2="cyan"):
        """Creates a simple placeholder icon (circle with gradient-like look)."""
        image = Image.new('RGB', (width, height), color=(0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        # Simple circle for the icon
        dc.ellipse([8, 8, width-8, height-8], fill=color1, outline=color2, width=2)
        # Small inner dot
        dc.ellipse([width//2-10, height//2-10, width//2+10, height//2+10], fill=color2)
        return image

    def toggle_console(self, icon, item):
        """Toggles the visibility of the console window."""
        if self.console_window:
            window_title = win32gui.GetWindowText(self.console_window)
            if self.console_visible:
                win32gui.ShowWindow(self.console_window, win32con.SW_HIDE)
                self.console_visible = False
                logger.info(f"Console hidden (Window: '{window_title}').")
            else:
                win32gui.ShowWindow(self.console_window, win32con.SW_SHOW)
                win32gui.SetForegroundWindow(self.console_window)
                self.console_visible = True
                logger.info(f"Console shown (Window: '{window_title}').")
        else:
            logger.error("Could not find console window handle.")

    def set_autostart(self, icon, item):
        """Toggle autostart status."""
        new_state = not item.checked
        result = manage_autostart(enable=new_state)
        logger.info(result)

    def on_quit(self, icon, item):
        """Called when 'Quit' is clicked in the tray menu."""
        logger.info("Quitting via System Tray...")
        # Ensure console is visible before quitting to avoid ghost processes
        if not self.console_visible and self.console_window:
            win32gui.ShowWindow(self.console_window, win32con.SW_SHOW)
        
        icon.stop()
        if self.on_stop_callback:
            self.on_stop_callback()

    def run(self):
        """Initializes and runs the tray icon in its own loop."""
        
        def is_autostart_enabled(item):
            return is_autostart_enabled_check()

        menu = pystray.Menu(
            pystray.MenuItem('Jarvis AI Assistant', lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda text: "Show Console" if not self.console_visible else "Hide Console",
                self.toggle_console
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Autostart",
                self.set_autostart,
                checked=is_autostart_enabled
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', self.on_quit)
        )
        
        self.icon = pystray.Icon(
            "jarvis",
            icon=self.create_image(),
            title="Jarvis AI Assistant",
            menu=menu
        )
        
        self.icon.run()

    def start(self):
        """Starts the tray icon in a separate thread."""
        self.icon_thread = threading.Thread(target=self.run, daemon=True)
        self.icon_thread.start()

    def stop(self):
        """Stops the icon thread."""
        if self.icon:
            self.icon.stop()
