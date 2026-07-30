import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add the project root to sys.path to allow importing from core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QDialog
from core.ui.security_ui import SecurityDialog


class TestSecurityDialog(unittest.TestCase):
    @patch("core.ui.security_ui.QDialog.exec")
    def test_initialization_and_ask_accept(self, mock_exec):
        mock_exec.return_value = QDialog.DialogCode.Accepted
        dialog = SecurityDialog("test action")
        self.assertEqual(dialog.action_desc, "test action")
        result = dialog.ask()
        self.assertTrue(result)
        self.assertTrue(dialog.result)
        self.assertTrue(dialog.confirmed_event.is_set())

    @patch("core.ui.security_ui.QDialog.exec")
    def test_ask_reject(self, mock_exec):
        mock_exec.return_value = QDialog.DialogCode.Rejected
        dialog = SecurityDialog("test action")
        result = dialog.ask()
        self.assertFalse(result)
        self.assertFalse(dialog.result)
        self.assertTrue(dialog.confirmed_event.is_set())

    def test_close_programmatically(self):
        dialog = SecurityDialog("test action")
        dialog.close()
        self.assertTrue(dialog.confirmed_event.is_set())
        self.assertFalse(dialog.result)


if __name__ == "__main__":
    unittest.main()

