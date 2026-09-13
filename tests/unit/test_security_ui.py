import os
import sys
import unittest
from unittest.mock import patch

# Add the project root to sys.path to allow importing from core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication, QDialog

from core.ui.security_ui import SecurityDialog


class TestSecurityDialog(unittest.TestCase):
    @patch("core.ui.security_ui.QDialog.exec")
    def test_initialization_and_ask_accept(self, mock_exec):
        mock_exec.return_value = QDialog.DialogCode.Accepted
        dialog = SecurityDialog("test action")
        self.assertEqual(dialog.action_desc, "test action")
        result = dialog.ask()
        self.assertTrue(result)
        self.assertTrue(dialog.user_result)
        self.assertTrue(dialog.confirmed_event.is_set())

    @patch("core.ui.security_ui.QDialog.exec")
    def test_ask_reject(self, mock_exec):
        mock_exec.return_value = QDialog.DialogCode.Rejected
        dialog = SecurityDialog("test action")
        result = dialog.ask()
        self.assertFalse(result)
        self.assertFalse(dialog.user_result)
        self.assertTrue(dialog.confirmed_event.is_set())

    def test_close_programmatically(self):
        dialog = SecurityDialog("test action")
        dialog.close()
        self.assertTrue(dialog.confirmed_event.is_set())
        self.assertFalse(dialog.user_result)


class TestSecurityDialogManager(unittest.TestCase):
    def setUp(self):
        # Ensure a QApplication instance exists
        self.app = QApplication.instance()
        if not self.app:
            self.app = QApplication([])

    def test_manager_on_show_and_approve(self):
        from threading import Event

        from core.ui.security_ui import SecurityDialogManager

        manager = SecurityDialogManager()
        result_box = {"result": False}
        done_event = Event()

        # Trigger show
        with (
            patch.object(QDialog, "show") as mock_show,
            patch.object(QDialog, "raise_"),
            patch.object(QDialog, "activateWindow"),
        ):
            manager._on_show_dialog("Test Action", result_box, done_event)
            mock_show.assert_called_once()
            self.assertIsNotNone(manager.active_dialog)

            # Test external approve triggers accept
            with patch.object(manager.active_dialog, "accept") as mock_accept:
                manager._on_approve()
                mock_accept.assert_called_once()

    def test_manager_on_show_and_reject(self):
        from threading import Event

        from core.ui.security_ui import SecurityDialogManager

        manager = SecurityDialogManager()
        result_box = {"result": False}
        done_event = Event()

        with (
            patch.object(QDialog, "show"),
            patch.object(QDialog, "raise_"),
            patch.object(QDialog, "activateWindow"),
        ):
            manager._on_show_dialog("Test Action", result_box, done_event)
            self.assertIsNotNone(manager.active_dialog)

            with patch.object(manager.active_dialog, "reject") as mock_reject:
                manager._on_reject()
                mock_reject.assert_called_once()

    def test_manager_finished_handler_sets_result_before_event(self):
        from threading import Event

        from core.ui.security_ui import SecurityDialogManager

        manager = SecurityDialogManager()
        result_box = {"result": False}
        done_event = Event()

        with (
            patch.object(QDialog, "show"),
            patch.object(QDialog, "raise_"),
            patch.object(QDialog, "activateWindow"),
        ):
            manager._on_show_dialog("Test Action", result_box, done_event)

            # Simulate finished with Accepted
            active_dialog = manager.active_dialog
            self.assertIsNotNone(active_dialog)
            active_dialog.finished.emit(int(QDialog.DialogCode.Accepted))

            self.assertTrue(result_box["result"])
            self.assertTrue(done_event.is_set())
            self.assertIsNone(manager.active_dialog)

    def test_manager_timeout(self):
        import threading

        from core.ui.security_ui import SecurityDialogManager

        manager = SecurityDialogManager()

        # Emulate calling from a secondary thread with immediate timeout
        result = [None]

        def worker():
            result[0] = manager.ask_authorization("Test Action", timeout=0.01)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        self.assertFalse(result[0])

    def test_security_dialog_secondary_thread_delegation(self):
        import threading

        from core.ui.security_ui import SecurityDialog, get_security_dialog_manager

        manager = get_security_dialog_manager()
        self.assertIsNotNone(manager)

        dialog = SecurityDialog("secondary thread action")
        result = [None]

        with patch.object(manager, "ask_authorization", return_value=True) as mock_ask:

            def worker():
                result[0] = dialog.ask()

            t = threading.Thread(target=worker)
            t.start()
            t.join()

            mock_ask.assert_called_once_with("secondary thread action", timeout=45.0)
            self.assertTrue(result[0])
            self.assertTrue(dialog.user_result)
            self.assertTrue(dialog.confirmed_event.is_set())


if __name__ == "__main__":
    unittest.main()
