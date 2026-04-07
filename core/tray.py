import pystray
from PIL import Image, ImageDraw
import threading
from core.logger_config import logger

class JarvisTray:
    def __init__(self, on_stop_callback):
        self.on_stop_callback = on_stop_callback
        self.icon = None
        self.icon_thread = None

    def create_image(self, width=64, height=64, color1="blue", color2="cyan"):
        """Creates a simple placeholder icon (circle with gradient-like look)."""
        image = Image.new('RGB', (width, height), color=(0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        # Simple circle for the icon
        dc.ellipse([8, 8, width-8, height-8], fill=color1, outline=color2, width=2)
        # Small inner dot
        dc.ellipse([width//2-10, height//2-10, width//2+10, height//2+10], fill=color2)
        return image

    def on_quit(self, icon, item):
        """Called when 'Quit' is clicked in the tray menu."""
        logger.info("Quitting via System Tray...")
        icon.stop()
        if self.on_stop_callback:
            self.on_stop_callback()

    def run(self):
        """Initializes and runs the tray icon in its own loop."""
        menu = pystray.Menu(
            pystray.MenuItem('Jarvis AI Assistant', lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', self.on_quit)
        )
        
        self.icon = pystray.Icon(
            "jarvis",
            icon=self.create_image(),
            title="Jarvis AI Assistant",
            menu=menu
        )
        
        # This is a blocking call, so it should run in its own thread
        self.icon.run()

    def start(self):
        """Starts the tray icon in a separate thread."""
        self.icon_thread = threading.Thread(target=self.run, daemon=True)
        self.icon_thread.start()

    def stop(self):
        """Stops the icon thread."""
        if self.icon:
            self.icon.stop()
