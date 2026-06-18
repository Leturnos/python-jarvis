import os

# Unified Default LLM Configs
DEFAULT_PROVIDER = "openrouter"
DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "deepseek": "deepseek-chat",
    "openrouter": "openrouter/google/gemini-2.5-flash",  # Explicit provider prefix for LiteLLM routing safety
}


# Application Registry (Resolves duplicates between automator & dispatcher)
class AppRegistry:
    SPOTIFY_PROCESS = "spotify.exe"
    SPOTIFY_APP_NAME = "spotify"
    SPOTIFY_WINDOW_TITLES = {"spotify", "spotify premium", "spotify free"}

    WARP_PROCESS = "warp"
    WARP_APP_NAME = "warp"
    WARP_NEW_TAB_SHORTCUT = ["ctrl", "shift", "t"]
    WARP_WINDOW_FALLBACKS = ["ready", "working", "mvp"]

    ACTIVE_WINDOW_SAFETY_FALLBACKS = {"terminal", "cmd", "powershell"}


# UI and Execution Timing (Sleeps, delays, and intervals)
class Timing:
    UI_STABILIZATION_SHORT = 0.1  # Fast stability checks
    UI_STABILIZATION_MEDIUM = 0.3  # Standard UI transition wait
    UI_STABILIZATION_LONG = 0.5  # Focus/recovery delays

    WARP_STARTUP_DELAY = 2.0  # Startup delay for Warp process
    WARP_TAB_CREATION = 1.2  # Delay for Warp tab animations
    WARP_CMD_EXECUTION = 0.6  # Typing execution interval

    WINDOW_SEARCH_SLEEP = 0.2  # Polling delay during window loops
    WINDOW_RECOVERY_SLEEP = 0.4  # Yield time during window restoration
    POST_FOCUS_RENDER_SLEEP = 0.5  # Wait time after gaining focus before screenshotting
    AUTOPLAY_CLICK_DELAY = 1.8  # Timing delay to trigger auto-play actions

    MOUSE_DETECT_POLLING = 0.1  # Mouse position polling loop delay


# Spotify Computer Vision Constants
class SpotifyCV:
    # HSV Color range for active green play button (Spotify brand green)
    GREEN_HSV_LOWER = [55, 100, 100]
    GREEN_HSV_UPPER = [85, 255, 255]

    # Geometry and Aspect filters
    PLAY_BUTTON_ASPECT_RATIO_MIN = 0.75
    PLAY_BUTTON_ASPECT_RATIO_MAX = 1.25
    PLAY_BUTTON_MIN_AREA_FACTOR = 80
    PLAY_BUTTON_MAX_AREA_FACTOR = 8000


# OS & Environment Constants
EXCLUDED_WINDOW_CLASSES = ("Progman", "WorkerW", "Shell_TrayWnd")
DEFAULT_HISTORY_DB = "data/history.db"
WAKE_WORD_MODELS_PATH = os.path.join("models", "*.onnx")

# Autostart / Startup Registry Keys
REGISTRY_AUTOSTART_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_APP_NAME = "JarvisAI"
AUTOSTART_SHORTCUT_NAME = "Jarvis.lnk"
AUTOSTART_LAUNCHER_NAME = "launcher.vbs"
AUTOSTART_COMMAND = "uv run main.py --hidden"
AUTOSTART_WINDOW_STYLE = 7  # Minimized
AUTOSTART_DESCRIPTION = "Jarvis AI Assistant"

# SAPI5 TTS Engine Constants
DEFAULT_SAPI5_VOICE = "maria"
DEFAULT_SAPI5_LANGS = ["portuguese", "brazil"]
DEFAULT_TTS_RATE = 2
DEFAULT_TTS_VOLUME = 100
