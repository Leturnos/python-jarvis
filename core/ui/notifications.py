"""Hybrid Windows & Desktop HUD notification dispatcher for Jarvis."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from core.activation import is_foreground_fullscreen, is_screen_locked
from core.infra.config import config
from core.infra.logger_config import logger
from core.shared.utils import get_resources_dir
from core.ui.desktop_notifications import DesktopNotificationManager

try:
    from plyer import notification as _plyer_notification
except ImportError:
    _plyer_notification = None


_TRAY_ICON_MAP: dict[str, QSystemTrayIcon.MessageIcon] = {
    "info": QSystemTrayIcon.MessageIcon.Information,
    "success": QSystemTrayIcon.MessageIcon.Information,
    "warning": QSystemTrayIcon.MessageIcon.Warning,
    "error": QSystemTrayIcon.MessageIcon.Critical,
}


class NotificationBridge(QObject):
    """Thread-safe GUI bridge routing backend notifications to Desktop HUD or Tray."""

    notify_requested = Signal(str, str, int, str, bool, object)

    def __init__(
        self,
        tray_icon: QSystemTrayIcon | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._tray_icon: QSystemTrayIcon | None = tray_icon
        self._desktop_mgr = DesktopNotificationManager(self)
        self.notify_requested.connect(self._on_notify_requested)

        if tray_icon is not None:
            tray_icon.destroyed.connect(self._on_tray_destroyed)

    def set_tray_icon(self, tray_icon: QSystemTrayIcon | None) -> None:
        self._tray_icon = tray_icon
        if tray_icon is not None:
            tray_icon.destroyed.connect(self._on_tray_destroyed)

    def _on_tray_destroyed(self) -> None:
        self._tray_icon = None

    def clear_desktop_toasts(self) -> None:
        self._desktop_mgr.clear_all()

    def _on_notify_requested(
        self,
        title: str,
        message: str,
        duration_sec: int,
        level: str,
        force_tray: bool,
        on_click: Any = None,
    ) -> None:
        try:
            if is_screen_locked():
                logger.debug(f"Screen is locked; skipping notification '{title}'.")
                return

            raw_notif = config.get("notifications")
            notif_cfg = raw_notif if isinstance(raw_notif, dict) else {}
            mode = str(notif_cfg.get("mode", "hybrid")).lower()
            is_fullscreen = is_foreground_fullscreen()
            use_tray = (
                force_tray or mode == "tray" or (mode == "hybrid" and is_fullscreen)
            )

            if use_tray:
                if self._tray_icon is not None and self._tray_icon.isVisible():
                    try:
                        tray_icon_obj = self._tray_icon.icon()
                        use_brand_icon = (
                            level.lower() in ("info", "success")
                            and tray_icon_obj is not None
                            and not tray_icon_obj.isNull()
                        )
                        icon_arg: Any = (
                            tray_icon_obj
                            if use_brand_icon
                            else _TRAY_ICON_MAP.get(
                                level.lower(), QSystemTrayIcon.MessageIcon.Information
                            )
                        )
                        self._tray_icon.showMessage(
                            title,
                            message,
                            icon_arg,
                            max(1500, duration_sec * 1000),
                        )
                        return
                    except Exception as e:
                        logger.warning(f"Tray notification failed: {e}")

                # Respect explicit tray-only preference or fullscreen isolation
                if mode == "tray" or is_fullscreen:
                    return

            hud_kwargs: dict[str, Any] = {
                "title": title,
                "message": message,
                "duration_ms": max(1500, duration_sec * 1000),
                "level": level,
            }
            if callable(on_click):
                hud_kwargs["on_click"] = on_click
            self._desktop_mgr.show_notification(**hud_kwargs)
        except Exception as e:
            logger.error(f"Error handling notification '{title}': {e}")


_notification_bridge: NotificationBridge | None = None


def _on_bridge_destroyed() -> None:
    global _notification_bridge
    _notification_bridge = None


def register_notification_bridge(
    tray_icon: QSystemTrayIcon | None = None,
    parent: QObject | None = None,
) -> NotificationBridge | None:
    """Initializes or updates the GUI-thread NotificationBridge."""
    global _notification_bridge
    app = QApplication.instance()
    if app is None:
        return None
    if threading.current_thread() is not threading.main_thread():
        return _notification_bridge

    if _notification_bridge is not None:
        try:
            _notification_bridge.objectName()
        except RuntimeError:
            _notification_bridge = None

    if _notification_bridge is None:
        _notification_bridge = NotificationBridge(
            tray_icon=tray_icon,
            parent=parent or app,
        )
        _notification_bridge.destroyed.connect(_on_bridge_destroyed)
    else:
        _notification_bridge.set_tray_icon(tray_icon)
    return _notification_bridge


def clear_notification_bridge() -> None:
    """Clears active desktop toasts and detaches the bridge (e.g., on app exit)."""
    global _notification_bridge
    bridge = _notification_bridge
    _notification_bridge = None
    if bridge is not None:
        try:
            bridge.clear_desktop_toasts()
            bridge.set_tray_icon(None)
            bridge.deleteLater()
        except RuntimeError:
            pass
        except Exception:
            pass


def _notify_plyer_fallback(title: str, message: str, duration: int) -> None:
    """Fallback notification with Jarvis icon when GUI loop/bridge is unavailable."""
    if _plyer_notification is None:
        return
    try:
        icon_path = get_resources_dir() / "icon.ico"
        kwargs: dict[str, Any] = {
            "title": title,
            "message": message,
            "app_name": "Jarvis",
            "timeout": duration,
        }
        if icon_path.exists():
            kwargs["app_icon"] = str(icon_path)
        _plyer_notification.notify(**kwargs)
    except Exception as e:
        logger.error(f"Failed to show fallback notification via Plyer: {e}")


class JarvisNotifier:
    """Routes Jarvis notifications cleanly through the hybrid HUD + Tray pipeline."""

    def __init__(self) -> None:
        pass

    def notify(
        self,
        title: str,
        message: str,
        duration: int = 3,
        *,
        level: str = "info",
        force_tray: bool = False,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        """Sends a desktop HUD or system tray notification in a thread-safe manner."""
        bridge = _notification_bridge
        if bridge is not None and QApplication.instance() is not None:
            try:
                bridge.notify_requested.emit(
                    str(title),
                    str(message),
                    int(duration),
                    str(level),
                    bool(force_tray),
                    on_click,
                )
                return
            except Exception as e:
                logger.warning(f"NotificationBridge emit failed, using fallback: {e}")

        _notify_plyer_fallback(str(title), str(message), int(duration))
