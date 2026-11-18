"""Tests for JarvisToast (1A), AudioCalibrationDialog (2A), Hybrid Notifications (3A+3B), and copy formatting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtCore import QEvent, QPointF, QRect
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QSystemTrayIcon

from core.execution.step_executor import notify_partial_failure
from core.ui.command_palette_qt import QtCommandPalette, QtCommandPaletteDialog
from core.ui.desktop_notifications import DesktopNotificationManager
from core.ui.feedback import (
    JarvisToastManager,
    format_proactivity_label,
    format_provider_name,
    show_error,
    show_info,
    show_success,
    show_warning,
)
from core.ui.main_window import MainWindow
from core.ui.notifications import (
    JarvisNotifier,
    clear_notification_bridge,
    register_notification_bridge,
)
from core.ui.widgets.audio_calibration_dialog import AudioCalibrationDialog


def test_format_provider_name_and_proactivity_label() -> None:
    assert format_provider_name("openai") == "OpenAI"
    assert format_provider_name("openrouter") == "OpenRouter"
    assert format_provider_name("deepseek") == "DeepSeek"
    assert format_provider_name("gemini") == "Gemini"
    assert format_provider_name("anthropic") == "Anthropic"
    assert format_provider_name("custom") == "Custom"

    assert format_proactivity_label("objective") == "Objetiva"
    assert format_proactivity_label("proactive") == "Proativa"


def test_jarvis_toast_fits_inside_main_window_without_titlebar_collision() -> None:
    app = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()

    window = MainWindow(ui_adapter)
    window.show()
    app.processEvents()

    toast = show_success(
        "Preferências da IA salvas",
        "Cidade: São Paulo • Postura: Objetiva com frases longas e informativas para validar quebra automática.",
        parent=window.settings_tab,
    )
    assert toast is not None
    app.processEvents()

    assert toast.width() <= 470
    assert toast.x() >= 8
    assert toast.x() + toast.width() <= window.width() - 8
    assert toast.y() >= window.title_bar.height()
    assert toast.y() + toast.height() <= window.height()

    toast.dismiss()
    toast.dismiss()
    app.processEvents()
    window.close()


def test_jarvis_toast_severity_accents_and_hover_preserves_long_duration() -> None:
    _ = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()
    window = MainWindow(ui_adapter)

    t_info = show_info("Info", "Mensagem informativa", parent=window, duration=9000)
    t_warn = show_warning("Aviso", "Mensagem de alerta", parent=window)
    t_err = show_error("Erro", "Mensagem de erro", parent=window)

    assert t_info is not None and "#4cc2ff" in t_info.styleSheet()
    assert t_warn is not None and "#f39c12" in t_warn.styleSheet()
    assert t_err is not None and "#ff3b5c" in t_err.styleSheet()

    enter_ev = QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10))
    t_info.enterEvent(enter_ev)
    assert not t_info._auto_timer.isActive()
    t_info.leaveEvent(QEvent(QEvent.Type.Leave))
    assert t_info._auto_timer.isActive()
    assert t_info._auto_timer.interval() > 5000

    for t in (t_info, t_warn, t_err):
        t.dismiss()


def test_jarvis_toast_manager_evicts_excess_beyond_max_visible() -> None:
    app = QApplication.instance() or QApplication([])
    ui_adapter = MagicMock()
    ui_adapter.wakeword_name = "Hey Jarvis"
    ui_adapter.visual_state_updated.connect = MagicMock()
    window = MainWindow(ui_adapter)
    mgr = JarvisToastManager()

    created = [
        mgr.show("info", f"Toast {i}", "Corpo curto", parent=window, duration=5000)
        for i in range(mgr.MAX_VISIBLE + 2)
    ]
    app.processEvents()

    assert len(mgr._toasts_by_host[window]) == mgr.MAX_VISIBLE
    assert created[0]._is_closing is True
    assert created[1]._is_closing is True
    assert created[-1]._is_closing is False

    for item in created[2:]:
        item.dismiss()


def test_audio_calibration_dialog_uses_frameless_obsidian_titlebar_and_rejects() -> (
    None
):
    _ = QApplication.instance() or QApplication([])
    dlg = AudioCalibrationDialog()
    assert hasattr(dlg, "shell_frame")
    assert hasattr(dlg, "title_bar")
    assert dlg.title_bar.title_label.text() == "Calibração de Microfone"

    rejected_signals: list[bool] = []
    dlg.rejected.connect(lambda: rejected_signals.append(True))
    dlg.title_bar.close_btn.click()

    assert rejected_signals == [True]
    assert dlg.result() == int(QDialog.DialogCode.Rejected)


def test_command_palette_dialog_has_obsidian_shell_frame() -> None:
    _ = QApplication.instance() or QApplication([])
    palette = QtCommandPalette(dispatcher=MagicMock())
    dlg = QtCommandPaletteDialog(palette)
    assert hasattr(dlg, "shell_frame")
    assert dlg.shell_frame.objectName() == "CommandPaletteShell"
    dlg.close()


def test_desktop_notification_manager_stacks_bottom_right() -> None:
    _ = QApplication.instance() or QApplication([])
    mgr = DesktopNotificationManager()
    with patch.object(mgr, "_screen_geometry", return_value=QRect(0, 0, 1920, 1040)):
        c1 = mgr.show_notification(
            "Jarvis", "Primeiro aviso", duration_ms=5000, level="info"
        )
        c2 = mgr.show_notification(
            "Jarvis", "Segundo aviso", duration_ms=5000, level="success"
        )
        QTest.qWait(260)
        assert c1.x() == 1920 - c1.width() - mgr.MARGIN_X
        assert c2.x() == 1920 - c2.width() - mgr.MARGIN_X
        assert c1.y() < c2.y()
    mgr.clear_all()
    QTest.qWait(220)


def test_hybrid_notification_routes_desktop_vs_fullscreen_tray_and_guards() -> None:
    app = QApplication.instance() or QApplication([])
    clear_notification_bridge()

    mock_tray = MagicMock(spec=QSystemTrayIcon)
    mock_tray.destroyed = MagicMock()
    mock_tray.isVisible.return_value = True
    bridge = register_notification_bridge(tray_icon=mock_tray, parent=app)
    assert bridge is not None

    try:
        # 1. Desktop free + hybrid -> Desktop HUD (3B)
        with (
            patch("core.ui.notifications.is_screen_locked", return_value=False),
            patch("core.ui.notifications.is_foreground_fullscreen", return_value=False),
            patch(
                "core.ui.notifications.config",
                {"notifications": {"mode": "hybrid"}},
            ),
            patch.object(bridge._desktop_mgr, "show_notification") as mock_hud,
        ):
            JarvisNotifier().notify(
                "Timer", "Tempo esgotado!", duration=5, level="info"
            )
            app.processEvents()
            mock_hud.assert_called_once_with(
                title="Timer",
                message="Tempo esgotado!",
                duration_ms=5000,
                level="info",
            )
            mock_tray.showMessage.assert_not_called()

        # 2. Fullscreen active -> routes to visible Tray (3A) without Desktop HUD
        mock_tray.reset_mock()
        mock_tray.isVisible.return_value = True
        with (
            patch("core.ui.notifications.is_screen_locked", return_value=False),
            patch("core.ui.notifications.is_foreground_fullscreen", return_value=True),
            patch(
                "core.ui.notifications.config",
                {"notifications": {"mode": "hybrid"}},
            ),
            patch.object(bridge._desktop_mgr, "show_notification") as mock_hud,
        ):
            JarvisNotifier().notify(
                "Jarvis", "Aviso em jogo", duration=4, level="warning"
            )
            app.processEvents()
            mock_hud.assert_not_called()
            mock_tray.showMessage.assert_called_once()

        # 3. mode='tray' with hidden tray -> never leaks Desktop HUD
        mock_tray.reset_mock()
        mock_tray.isVisible.return_value = False
        with (
            patch("core.ui.notifications.is_screen_locked", return_value=False),
            patch("core.ui.notifications.is_foreground_fullscreen", return_value=False),
            patch(
                "core.ui.notifications.config",
                {"notifications": {"mode": "tray"}},
            ),
            patch.object(bridge._desktop_mgr, "show_notification") as mock_hud,
        ):
            JarvisNotifier().notify("Jarvis", "Somente bandeja", level="info")
            app.processEvents()
            mock_hud.assert_not_called()
            mock_tray.showMessage.assert_not_called()

        # 4. force_tray=True routes directly to visible Tray
        mock_tray.reset_mock()
        mock_tray.isVisible.return_value = True
        with (
            patch("core.ui.notifications.is_screen_locked", return_value=False),
            patch("core.ui.notifications.is_foreground_fullscreen", return_value=False),
            patch(
                "core.ui.notifications.config",
                {"notifications": {"mode": "hybrid"}},
            ),
            patch.object(bridge._desktop_mgr, "show_notification") as mock_hud,
        ):
            JarvisNotifier().notify("Update", "Nova versão", force_tray=True)
            app.processEvents()
            mock_hud.assert_not_called()
            mock_tray.showMessage.assert_called_once()

        # 5. Lock screen suppresses notifications completely
        mock_tray.reset_mock()
        with (
            patch("core.ui.notifications.is_screen_locked", return_value=True),
            patch.object(bridge._desktop_mgr, "show_notification") as mock_hud,
        ):
            JarvisNotifier().notify("Jarvis", "Privado", level="info")
            app.processEvents()
            mock_hud.assert_not_called()
            mock_tray.showMessage.assert_not_called()

        # 6. Null notifications config section does not raise inside slot
        with (
            patch("core.ui.notifications.is_screen_locked", return_value=False),
            patch("core.ui.notifications.is_foreground_fullscreen", return_value=False),
            patch("core.ui.notifications.config", {"notifications": None}),
            patch.object(bridge._desktop_mgr, "show_notification") as mock_hud,
        ):
            JarvisNotifier().notify("Jarvis", "Config vazia", level="info")
            app.processEvents()
            mock_hud.assert_called_once()
    finally:
        clear_notification_bridge()


def test_notifier_uses_plyer_fallback_with_icon_when_no_bridge() -> None:
    clear_notification_bridge()
    with patch("core.ui.notifications._plyer_notification") as mock_plyer:
        JarvisNotifier().notify("Jarvis", "Fallback inicial", duration=3)
        mock_plyer.notify.assert_called_once()
        _, kwargs = mock_plyer.notify.call_args
        assert kwargs["title"] == "Jarvis"
        assert kwargs["message"] == "Fallback inicial"
        assert kwargs["app_name"] == "Jarvis"


def test_notify_partial_failure_uses_portuguese_via_jarvis_notifier() -> None:
    with patch("core.execution.step_executor.JarvisNotifier") as mock_cls:
        notify_partial_failure("Spotify", "Janela não respondeu")
        mock_cls.return_value.notify.assert_called_once_with(
            title="Jarvis — Aviso de Execução",
            message="Não foi possível preparar 'Spotify': Janela não respondeu",
            duration=4,
            level="warning",
        )
