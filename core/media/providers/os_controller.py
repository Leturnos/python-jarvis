import pyautogui

from core.media.models import MediaAction


class OSMediaController:
    MAP = {
        MediaAction.PLAY: "playpause",
        MediaAction.PAUSE: "playpause",
        MediaAction.NEXT: "nexttrack",
        MediaAction.PREV: "prevtrack",
    }

    @staticmethod
    def send_command(action: MediaAction) -> bool:
        key = OSMediaController.MAP.get(action)
        if key:
            pyautogui.press(key)
            return True
        return False
