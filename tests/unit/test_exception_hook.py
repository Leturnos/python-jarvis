from unittest.mock import MagicMock, patch

from main import qt_exception_hook


def test_qt_exception_hook_logs_error_and_notifies():
    mock_notifier_inst = MagicMock()
    exctype = ValueError
    value = ValueError("test error message")
    tb = MagicMock()

    with (
        patch("main.logger.error") as mock_logger_error,
        patch(
            "main.JarvisNotifier", return_value=mock_notifier_inst
        ) as mock_notifier_cls,
        patch("sys.__excepthook__") as mock_sys_excepthook,
    ):
        qt_exception_hook(exctype, value, tb)

        # 1. logger.error is called with exc_info
        mock_logger_error.assert_called_once_with(
            "Uncaught Qt Exception:", exc_info=(exctype, value, tb)
        )

        # 2. notifier.notify is called with title and message
        mock_notifier_cls.assert_called_once()
        mock_notifier_inst.notify.assert_called_once_with(
            title="Jarvis - Erro Inesperado",
            message="Ocorreu um erro: test error message. Verifique os logs para detalhes.",
        )

        # 3. sys.__excepthook__ is called
        mock_sys_excepthook.assert_called_once_with(exctype, value, tb)


def test_qt_exception_hook_notifier_exception_does_not_prevent_excepthook():
    mock_notifier_inst = MagicMock()
    mock_notifier_inst.notify.side_effect = RuntimeError("Notification service down")
    exctype = RuntimeError
    value = RuntimeError("unhandled crash")
    tb = MagicMock()

    with (
        patch("main.logger.error") as mock_logger_error,
        patch("main.JarvisNotifier", return_value=mock_notifier_inst),
        patch("sys.__excepthook__") as mock_sys_excepthook,
    ):
        qt_exception_hook(exctype, value, tb)

        mock_logger_error.assert_called_once()
        mock_notifier_inst.notify.assert_called_once()
        # Ensure sys.__excepthook__ was still called despite notify error
        mock_sys_excepthook.assert_called_once_with(exctype, value, tb)
