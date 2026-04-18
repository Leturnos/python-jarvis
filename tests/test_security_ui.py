import unittest
from unittest.mock import MagicMock, patch
import threading
import time
import sys
import os

# Add the project root to sys.path to allow importing from core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.security_ui import SecurityDialog

class TestSecurityDialog(unittest.TestCase):
    @patch('core.security_ui.tk.Tk')
    def test_initialization(self, mock_tk):
        dialog = SecurityDialog("test action")
        self.assertEqual(dialog.action_desc, "test action")
        self.assertFalse(dialog.result)

    @patch('core.security_ui.tk.Tk')
    def test_ask_returns_result(self, mock_tk):
        # We need to simulate the user clicking a button which sets the event and destroys the window
        dialog = SecurityDialog("test action")
        
        def simulate_user_click():
            time.sleep(0.1)
            dialog.result = True
            dialog.confirmed_event.set()
            if dialog.root:
                # In mock, we need to quit the loop
                dialog.root.quit()

        threading.Thread(target=simulate_user_click).start()
        
        # In a real scenario, ask() calls root.mainloop()
        # For testing, we mock root.mainloop to wait for the event
        mock_root = mock_tk.return_value
        mock_root.mainloop.side_effect = lambda: dialog.confirmed_event.wait()
        
        result = dialog.ask()
        self.assertTrue(result)

    @patch('core.security_ui.tk.Tk')
    def test_close_programmatically(self, mock_tk):
        dialog = SecurityDialog("test action")
        
        mock_root = mock_tk.return_value
        dialog.root = mock_root
        
        # Mock after to call destroy immediately
        mock_root.after.side_effect = lambda ms, func: func()
        
        dialog.close()
        
        self.assertTrue(dialog.confirmed_event.is_set())
        self.assertFalse(dialog.result)
        mock_root.destroy.assert_called_once()

if __name__ == '__main__':
    unittest.main()
