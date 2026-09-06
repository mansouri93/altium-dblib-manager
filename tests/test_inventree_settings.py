# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from app.inventree.client import InvenTreeClient
from app.ui.inventree_settings_dialog import InvenTreeSettingsDialog

class TestInvenTreeSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        self.client = InvenTreeClient()

    def test_dialog_init_and_fields(self):
        dialog = InvenTreeSettingsDialog(self.client)
        self.assertEqual(dialog.windowTitle(), "InvenTree Connection Settings")
        
        # Check that UI elements exist
        self.assertIsNotNone(dialog.txt_base_url)
        self.assertIsNotNone(dialog.txt_username)
        self.assertIsNotNone(dialog.txt_password)
        self.assertIsNotNone(dialog.txt_api_token)
        self.assertIsNotNone(dialog.btn_test)
        self.assertIsNotNone(dialog.btn_save)

        # Toggle password visibility
        from PySide6.QtWidgets import QLineEdit
        self.assertEqual(dialog.txt_password.echoMode(), QLineEdit.EchoMode.Password)
        dialog._toggle_password_visibility()
        self.assertEqual(dialog.txt_password.echoMode(), QLineEdit.EchoMode.Normal)
        self.assertEqual(dialog.btn_toggle_pwd.text(), "Hide")
        dialog._toggle_password_visibility()
        self.assertEqual(dialog.txt_password.echoMode(), QLineEdit.EchoMode.Password)
        self.assertEqual(dialog.btn_toggle_pwd.text(), "Show")

        dialog.close()

    def test_client_reload_settings(self):
        # Initial state
        self.client._token = "dummy_token"
        self.client._location_cache[999] = "Test Loc"

        # Reload
        self.client.reload_settings()
        self.assertIsNone(self.client._token)
        self.assertEqual(len(self.client._location_cache), 0)

if __name__ == "__main__":
    unittest.main()
