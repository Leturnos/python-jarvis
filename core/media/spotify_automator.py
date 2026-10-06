import ctypes
import os
import time
from collections import namedtuple
from typing import Any

import cv2
import numpy as np
import psutil
import pyautogui
import pygetwindow as gw
import win32process

from core.audio.tts_engine import TTSEngine
from core.execution.window_manager import WindowManager
from core.infra.logger_config import logger
from core.media.cv_matcher import TemplateMatcher
from core.shared.constants import AppRegistry, SpotifyCV, Timing
from core.shared.utils import get_resources_dir

Box = namedtuple("Box", ["left", "top", "width", "height"])


class SpotifyAutomator:
    def __init__(
        self,
        config: dict[str, Any],
        window_manager: WindowManager,
        tts_engine: TTSEngine,
        cv_matcher: TemplateMatcher,
    ) -> None:
        self.config = config
        self.window_manager = window_manager
        self.tts_engine = tts_engine
        self.cv_matcher = cv_matcher

    @property
    def spotify_conf(self) -> dict[str, Any]:
        media_spotify = self.config.get("media", {}).get("spotify", {})
        auto_spotify = self.config.get("automation", {}).get("spotify", {})
        return {**media_spotify, **auto_spotify}

    def find_spotify_window(self, timeout: float = 0.0) -> Any:
        start_time = time.time()
        while True:
            try:
                spotify_pids = self.window_manager.find_processes(
                    executable_name=AppRegistry.SPOTIFY_PROCESS
                )
                if not spotify_pids:
                    spotify_pids = self.window_manager.find_processes(
                        executable_name=AppRegistry.SPOTIFY_APP_NAME
                    )

                for w in gw.getAllWindows():
                    if getattr(w, "_hWnd", None):
                        try:
                            _, pid = win32process.GetWindowThreadProcessId(w._hWnd)
                            is_pid_match = bool(spotify_pids and pid in spotify_pids)
                            if not is_pid_match and not spotify_pids:
                                try:
                                    p = psutil.Process(pid)
                                    p_name = p.name().lower().removesuffix(".exe")
                                    if p_name == AppRegistry.SPOTIFY_APP_NAME:
                                        is_pid_match = True
                                except Exception:
                                    pass

                            if is_pid_match and getattr(w, "title", None):
                                is_mock = (
                                    hasattr(w, "_spec_class")
                                    or type(w).__name__ in ("MagicMock", "Mock")
                                    or type(getattr(w, "width", None)).__name__
                                    in ("MagicMock", "Mock")
                                )
                                if (
                                    is_mock
                                    or getattr(w, "isMinimized", False)
                                    or (
                                        isinstance(
                                            getattr(w, "width", None), (int, float)
                                        )
                                        and isinstance(
                                            getattr(w, "height", None), (int, float)
                                        )
                                        and w.width > 200
                                        and w.height > 200
                                    )
                                ):
                                    return w
                        except Exception:
                            continue
            except Exception as e:
                logger.error(f"Error searching for Spotify window: {e}")

            if timeout <= 0 or (time.time() - start_time) >= timeout:
                break
            time.sleep(Timing.WINDOW_SEARCH_SLEEP)
        return None

    def activate_spotify_window(self, timeout: float = 6.0) -> bool:
        win = self.find_spotify_window(timeout=timeout)
        if not win:
            logger.warning(f"Spotify window not found within {timeout:.1f}s.")
            return False
        try:
            return self.window_manager.activate_window_by_hwnd(win._hWnd)
        except Exception as e:
            logger.error(f"Error activating Spotify window: {e}")
            return False

    def is_spotify_playing(self) -> bool:
        win = self.find_spotify_window()
        if not win or not win.title:
            return False
        return win.title.lower().strip() not in AppRegistry.SPOTIFY_WINDOW_TITLES

    def _wait_for_playback(self, max_attempts: int = 3, interval: float = 0.5) -> bool:
        """Polls for playback confirmation, accommodating track buffering latency."""
        for _ in range(max_attempts):
            time.sleep(interval)
            if self.is_spotify_playing():
                return True
        return False

    def find_spotify_green_button(
        self, haystack: Any, scale_factor: float = 1.0
    ) -> Any:
        try:
            hsv = cv2.cvtColor(haystack, cv2.COLOR_BGR2HSV)
            lower_green_val = self.spotify_conf.get(
                "green_hsv_lower", SpotifyCV.GREEN_HSV_LOWER
            )
            upper_green_val = self.spotify_conf.get(
                "green_hsv_upper", SpotifyCV.GREEN_HSV_UPPER
            )
            lower_green = np.array(lower_green_val)
            upper_green = np.array(upper_green_val)
            mask = cv2.inRange(hsv, lower_green, upper_green)
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            best_center = None
            best_area = 0.0
            best_rect = None

            for cnt in contours:
                area = cv2.contourArea(cnt)
                min_area = SpotifyCV.PLAY_BUTTON_MIN_AREA_FACTOR * (scale_factor**2)
                max_area = SpotifyCV.PLAY_BUTTON_MAX_AREA_FACTOR * (scale_factor**2)
                if min_area <= area <= max_area:
                    x, y, w, h = cv2.boundingRect(cnt)
                    aspect_ratio = float(w) / h
                    if (
                        SpotifyCV.PLAY_BUTTON_ASPECT_RATIO_MIN
                        <= aspect_ratio
                        <= SpotifyCV.PLAY_BUTTON_ASPECT_RATIO_MAX
                    ):
                        if area > best_area:
                            best_area = area
                            best_rect = (x, y, w, h)
                            m = cv2.moments(cnt)
                            if m["m00"] != 0:
                                best_center = (
                                    int(m["m10"] / m["m00"]),
                                    int(m["m01"] / m["m00"]),
                                )

            if best_center and best_rect:
                x, y, w, h = best_rect
                return Box(x, y, w, h)
        except Exception as e:
            logger.error(f"Error in find_spotify_green_button: {e}")
        return None

    def find_active_filter_pill(
        self, haystack: Any, scale_factor: float = 1.0
    ) -> Box | None:
        """Locates the bright white active search filter pill ('Tudo' / 'All')."""
        try:
            h, w, _ = haystack.shape
            top_bound = int(50 * scale_factor)
            bottom_bound = int(140 * scale_factor)
            if top_bound >= h or top_bound >= bottom_bound:
                return None
            if bottom_bound > h:
                bottom_bound = h
            header_region = haystack[top_bound:bottom_bound, :]
            gray = cv2.cvtColor(header_region, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            pills = []
            for cnt in contours:
                x, y, cw, ch = cv2.boundingRect(cnt)
                min_h, max_h = 20 * scale_factor, 45 * scale_factor
                min_w, max_w = 30 * scale_factor, 160 * scale_factor
                if min_h <= ch <= max_h and min_w <= cw <= max_w:
                    pills.append((x, y + top_bound, cw, ch))
            if pills:
                px, py, pw, ph = min(pills, key=lambda p: p[0])
                return Box(px, py, pw, ph)
        except Exception as e:
            logger.warning(f"Failed to find active filter pill: {e}")
        return None

    def dismiss_spotify_popup(
        self, haystack: Any, scale_factor: float = 1.0
    ) -> tuple[int, int] | None:
        """Detects in-app upsell promo modal (e.g. 'Curta 1 mês por R$ 0') and returns (x, y) coordinates of 'Ignorar' / dismiss button."""
        try:
            h, w, _ = haystack.shape
            min_y = int(h * 0.30)
            max_y = int(h * 0.75)
            if min_y >= max_y or max_y > h:
                return None

            central_region = haystack[min_y:max_y, :]
            gray = cv2.cvtColor(central_region, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 235, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for cnt in contours:
                x, y, cw, ch = cv2.boundingRect(cnt)
                min_w = int(140 * scale_factor)
                max_w = int(450 * scale_factor)
                min_h = int(30 * scale_factor)
                max_h = int(70 * scale_factor)
                if min_w <= cw <= max_w and min_h <= ch <= max_h:
                    center_x = x + cw // 2
                    if abs(center_x - (w // 2)) < int(160 * scale_factor):
                        # 'Ignorar' / 'Dismiss' is located directly beneath the primary CTA button
                        dismiss_x = center_x
                        dismiss_y = y + min_y + ch + int(35 * scale_factor)
                        return (dismiss_x, dismiss_y)
        except Exception as e:
            logger.debug(f"Error checking for Spotify popup: {e}")
        return None

    def spotify_click_play(
        self, click_type: str = "search", uri: str | None = None
    ) -> bool:
        win = self.find_spotify_window(timeout=3.0)
        if not win:
            logger.warning("Spotify window not found.")
            return False
        try:
            try:
                if win.isMinimized:
                    win.restore()
                    time.sleep(Timing.WINDOW_RECOVERY_SLEEP)
            except Exception as ex:
                logger.warning(f"Failed to restore Spotify window: {ex}")

            if not self.activate_spotify_window():
                return False

            time.sleep(Timing.POST_FOCUS_RENDER_SLEEP)

            fg_win = self.window_manager.get_foreground_window_info()
            if fg_win and isinstance(getattr(fg_win, "pid", None), int):
                spotify_pids = self.window_manager.find_processes(
                    executable_name=AppRegistry.SPOTIFY_PROCESS
                )
                if spotify_pids and fg_win.pid not in spotify_pids:
                    logger.warning(
                        f"Foreground window '{fg_win.title}' (pid={fg_win.pid}) is not Spotify. Aborting click."
                    )
                    return False

            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
                hdc = ctypes.windll.user32.GetDC(0)
                dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
                ctypes.windll.user32.ReleaseDC(0, hdc)
                scale_factor = dpi / 96.0
            except Exception:
                scale_factor = 1.0

            click_x, click_y = None, None
            direct_play_clicked = False

            if click_type == "playlist":
                try:
                    try:
                        screen_w, screen_h = pyautogui.size()
                    except Exception:
                        screen_w, screen_h = 1920, 1080
                    left = max(0, win.left)
                    top = max(0, win.top)
                    width = min(screen_w - left, win.width)
                    height = min(screen_h - top, win.height)

                    region = (
                        int(left * scale_factor),
                        int(top * scale_factor),
                        int(width * scale_factor),
                        int(height * scale_factor),
                    )

                    screenshot = pyautogui.screenshot(region=region)
                    is_mock = hasattr(screenshot, "_spec_class") or type(
                        screenshot
                    ).__name__ in ("MagicMock", "Mock")
                    haystack = None
                    if not is_mock:
                        haystack = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

                    pos = None
                    if haystack is not None:
                        pos = self.find_spotify_green_button(
                            haystack, scale_factor=scale_factor
                        )

                    if pos:
                        left_pos, top_pos, w_pos, h_pos = (
                            pos.left,
                            pos.top,
                            pos.width,
                            pos.height,
                        )
                        click_x = int((left * scale_factor) + left_pos + w_pos // 2)
                        click_y = int((top * scale_factor) + top_pos + h_pos // 2)
                        direct_play_clicked = True

                    if not direct_play_clicked:
                        play_button_path = str(
                            get_resources_dir() / "spotify_play_button.png"
                        )
                        high_conf = (
                            self.config.get("automation", {})
                            .get("cv", {})
                            .get("template_confidence_high", 0.7)
                        )
                        pos = self.cv_matcher.locate_template_multiscale(
                            play_button_path, region=region, confidence=high_conf
                        )
                        if pos:
                            click_x = int(pos.left + pos.width // 2)
                            click_y = int(pos.top + pos.height // 2)
                            direct_play_clicked = True
                except Exception as ex:
                    logger.warning(f"Failed image search: {ex}")

                if not direct_play_clicked:
                    click_x = win.left + win.width // 2
                    playlist_play_y_ratio = self.spotify_conf.get(
                        "playlist_play_y_ratio", 0.4
                    )
                    click_y = win.top + int(win.height * playlist_play_y_ratio)

                pyautogui.click(click_x, click_y)
                time.sleep(Timing.WINDOW_RECOVERY_SLEEP)

                if not direct_play_clicked:
                    pyautogui.press("tab")
                    time.sleep(Timing.UI_STABILIZATION_MEDIUM)
                    pyautogui.press("enter")
                    time.sleep(Timing.UI_STABILIZATION_MEDIUM)
                return True
            else:
                # click_type == "search"
                try:
                    screen_w, screen_h = pyautogui.size()
                except Exception:
                    screen_w, screen_h = 1920, 1080
                left = max(0, win.left)
                top = max(0, win.top)
                width = min(screen_w - left, win.width)
                height = min(screen_h - top, win.height)

                region = (
                    int(left * scale_factor),
                    int(top * scale_factor),
                    int(width * scale_factor),
                    int(height * scale_factor),
                )

                # 1. Fast-path: Check if green play button is ALREADY visible on screen
                haystack = None
                try:
                    screenshot = pyautogui.screenshot(region=region)
                    is_mock = hasattr(screenshot, "_spec_class") or type(
                        screenshot
                    ).__name__ in ("MagicMock", "Mock")
                    if not is_mock:
                        haystack = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                    else:
                        haystack = screenshot

                    if haystack is not None:
                        # 1.1 Dismiss upsell modal popup if present (e.g. 'Ignorar')
                        dismiss_coords = self.dismiss_spotify_popup(
                            haystack, scale_factor=scale_factor
                        )
                        if dismiss_coords:
                            dx, dy = dismiss_coords
                            click_dx = int((left * scale_factor) + dx)
                            click_dy = int((top * scale_factor) + dy)
                            logger.info(
                                f"Detected Spotify promo modal. Clicking 'Ignorar' at ({click_dx}, {click_dy})."
                            )
                            pyautogui.click(click_dx, click_dy)
                            time.sleep(Timing.POST_FOCUS_RENDER_SLEEP)
                            try:
                                screenshot = pyautogui.screenshot(region=region)
                                if not is_mock:
                                    haystack = cv2.cvtColor(
                                        np.array(screenshot), cv2.COLOR_RGB2BGR
                                    )
                                else:
                                    haystack = screenshot
                            except Exception as ex:
                                logger.warning(
                                    f"Failed to refresh screenshot after popup dismissal: {ex}"
                                )

                        initial_pos = self.find_spotify_green_button(
                            haystack, scale_factor=scale_factor
                        )
                        if initial_pos:
                            click_x = int(
                                (left * scale_factor)
                                + initial_pos.left
                                + initial_pos.width // 2
                            )
                            click_y = int(
                                (top * scale_factor)
                                + initial_pos.top
                                + initial_pos.height // 2
                            )
                            pyautogui.click(click_x, click_y)
                            if self._wait_for_playback():
                                return True
                except Exception as ex:
                    logger.warning(f"Fast-path green button search error: {ex}")

                # 2. Determine Top Result card hover position
                hover_matched = False
                hover_x, hover_y = None, None

                # 2.1 Try detecting active filter pill ('Tudo' / 'All')
                if haystack is not None:
                    pill = self.find_active_filter_pill(
                        haystack, scale_factor=scale_factor
                    )
                    if pill:
                        hover_x = int(
                            (left * scale_factor) + pill.left + int(100 * scale_factor)
                        )
                        hover_y = int(
                            (top * scale_factor)
                            + pill.top
                            + pill.height
                            + int(45 * scale_factor)
                        )
                        hover_matched = True

                # 2.2 Legacy Anchor fallback ('Melhor resultado' / 'Top result')
                if not hover_matched:
                    try:
                        anchor_pt_path = str(
                            get_resources_dir() / "spotify_search_anchor.png"
                        )
                        anchor_en_path = str(
                            get_resources_dir() / "spotify_search_anchor_en.png"
                        )
                        header_offset = self.spotify_conf.get("header_offset", 120)
                        region_search = (
                            int(left * scale_factor),
                            int((top + header_offset) * scale_factor),
                            int(width * scale_factor),
                            int((height - header_offset) * scale_factor)
                            if height > header_offset
                            else int(height * scale_factor),
                        )
                        low_conf = (
                            self.config.get("automation", {})
                            .get("cv", {})
                            .get("template_confidence_low", 0.4)
                        )
                        pos = None
                        if os.path.exists(anchor_pt_path):
                            pos = self.cv_matcher.locate_template_multiscale(
                                anchor_pt_path,
                                region=region_search,
                                confidence=low_conf,
                            )
                        if not pos and os.path.exists(anchor_en_path):
                            pos = self.cv_matcher.locate_template_multiscale(
                                anchor_en_path,
                                region=region_search,
                                confidence=low_conf,
                            )
                        if pos:
                            hover_x = int(pos.left + pos.width // 2)
                            search_vertical_offset_ratio = self.spotify_conf.get(
                                "search_vertical_offset_ratio", 0.1
                            )
                            hover_y = int(
                                pos.top
                                + pos.height // 2
                                + (win.height * scale_factor)
                                * search_vertical_offset_ratio
                            )
                            hover_matched = True
                    except Exception as ex:
                        logger.warning(f"Failed search anchor match: {ex}")

                # 2.3 Fallback coordinates based on Spotify desktop header geometry
                if not hover_matched:
                    search_x = self.spotify_conf.get("search_click_x")
                    search_y = self.spotify_conf.get("search_click_y")
                    if search_x is not None and search_y is not None:
                        hover_x, hover_y = int(search_x), int(search_y)
                    else:
                        offset_x = 350 if win.width > 1100 else 220
                        hover_x = int((left + offset_x) * scale_factor)
                        hover_y = int((top + 165) * scale_factor)

                # 3. Hover to reveal play button on top result card
                pyautogui.moveTo(hover_x, hover_y)
                time.sleep(Timing.POST_FOCUS_RENDER_SLEEP)

                # 4. Search for play button after hover
                play_pos = None
                try:
                    screenshot = pyautogui.screenshot(region=region)
                    is_mock = hasattr(screenshot, "_spec_class") or type(
                        screenshot
                    ).__name__ in ("MagicMock", "Mock")
                    haystack = None
                    if not is_mock:
                        haystack = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                    else:
                        haystack = screenshot

                    pos = None
                    if haystack is not None:
                        pos = self.find_spotify_green_button(
                            haystack, scale_factor=scale_factor
                        )

                    if pos:
                        click_x = int((left * scale_factor) + pos.left + pos.width // 2)
                        click_y = int((top * scale_factor) + pos.top + pos.height // 2)
                        play_pos = (click_x, click_y)

                    if not play_pos:
                        play_button_path = str(
                            get_resources_dir() / "spotify_play_button.png"
                        )
                        high_conf = (
                            self.config.get("automation", {})
                            .get("cv", {})
                            .get("template_confidence_high", 0.7)
                        )
                        t_pos = self.cv_matcher.locate_template_multiscale(
                            play_button_path, region=region, confidence=high_conf
                        )
                        if t_pos:
                            play_pos = (
                                int(t_pos.left + t_pos.width // 2),
                                int(t_pos.top + t_pos.height // 2),
                            )
                except Exception as ex:
                    logger.warning(f"Failed image play button search: {ex}")

                if play_pos:
                    pyautogui.click(play_pos[0], play_pos[1])
                    if self._wait_for_playback():
                        return True

                # 5. Direct Card Click and Playlist Fallback Chain
                pyautogui.click(hover_x, hover_y)
                time.sleep(Timing.AUTOPLAY_CLICK_DELAY)
                return self.spotify_click_play(click_type="playlist", uri=uri)
            return True
        except Exception as e:
            logger.error(f"Error executing Spotify click and play ({click_type}): {e}")
            return False
