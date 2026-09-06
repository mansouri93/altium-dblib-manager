# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from typing import Any
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
    QMessageBox,
    QFrame,
    QApplication,
)
from ..inventree.client import InvenTreeClient
from .icons import AppIcons

logger = logging.getLogger(__name__)

class InvenTreeSettingsDialog(QDialog):
    """
    Dialog for viewing and editing InvenTree API connection parameters
    including Server URL, Username, Password, and API Token.
    """

    def __init__(self, client: InvenTreeClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.client = client

        self.setWindowTitle("InvenTree Connection Settings")
        self.setMinimumWidth(460)
        self.setStyleSheet("""
            QDialog {
                background-color: #171724;
                color: #e0e0f0;
            }
            QLabel {
                color: #d0d0e6;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #212133;
                border: 1px solid #3d3d5c;
                border-radius: 4px;
                padding: 6px 10px;
                color: #ffffff;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #58a6ff;
                background-color: #26263d;
            }
            QPushButton {
                background-color: #26263b;
                color: #e0e0f0;
                border: 1px solid #3d3d5c;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #31314d;
                border-color: #58a6ff;
                color: #ffffff;
            }
            QPushButton#PrimaryButton {
                background-color: #1a56db;
                border: 1px solid #2563eb;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton#PrimaryButton:hover {
                background-color: #1d4ed8;
            }
        """)

        self._init_ui()
        self._load_current_values()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Header banner
        header_layout = QHBoxLayout()
        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(AppIcons.server().pixmap(28, 28))
        header_layout.addWidget(icon_lbl)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        lbl_title = QLabel("InvenTree Server Connection")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #58a6ff;")
        lbl_desc = QLabel("Configure server URL and credentials for warehouse inventory sync.")
        lbl_desc.setStyleSheet("font-size: 11.5px; color: #8f8fa8;")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_desc)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2b2b40;")
        main_layout.addWidget(sep)

        # Form Fields
        # 1. Base URL
        lbl_url = QLabel("Server Base URL:")
        lbl_url.setStyleSheet("font-weight: 500;")
        self.txt_base_url = QLineEdit(self)
        self.txt_base_url.setPlaceholderText("e.g. http://inventree.localhost:8180")
        main_layout.addWidget(lbl_url)
        main_layout.addWidget(self.txt_base_url)

        # 2. Username
        lbl_user = QLabel("Username:")
        lbl_user.setStyleSheet("font-weight: 500;")
        self.txt_username = QLineEdit(self)
        self.txt_username.setPlaceholderText("e.g. admin")
        main_layout.addWidget(lbl_user)
        main_layout.addWidget(self.txt_username)

        # 3. Password
        lbl_pwd = QLabel("Password:")
        lbl_pwd.setStyleSheet("font-weight: 500;")
        pwd_layout = QHBoxLayout()
        self.txt_password = QLineEdit(self)
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("Password")
        pwd_layout.addWidget(self.txt_password)

        self.btn_toggle_pwd = QPushButton("Show")
        self.btn_toggle_pwd.setFixedWidth(55)
        self.btn_toggle_pwd.clicked.connect(self._toggle_password_visibility)
        pwd_layout.addWidget(self.btn_toggle_pwd)

        main_layout.addWidget(lbl_pwd)
        main_layout.addLayout(pwd_layout)

        # 4. API Token
        lbl_token = QLabel("API Token (Optional):")
        lbl_token.setStyleSheet("font-weight: 500;")
        lbl_token_hint = QLabel("Leave empty to automatically authenticate with username & password.")
        lbl_token_hint.setStyleSheet("font-size: 11px; color: #7f7f98;")
        self.txt_api_token = QLineEdit(self)
        self.txt_api_token.setPlaceholderText("Optional token string...")
        main_layout.addWidget(lbl_token)
        main_layout.addWidget(lbl_token_hint)
        main_layout.addWidget(self.txt_api_token)

        # Test Connection Row
        test_layout = QHBoxLayout()
        self.btn_test = QPushButton(" Test Connection")
        self.btn_test.setIcon(AppIcons.sync_inventree())
        self.btn_test.clicked.connect(self._on_test_connection)
        test_layout.addWidget(self.btn_test)

        self.lbl_test_status = QLabel("")
        self.lbl_test_status.setStyleSheet("font-size: 11.5px;")
        test_layout.addWidget(self.lbl_test_status, stretch=1)
        main_layout.addLayout(test_layout)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save && Connect")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setIcon(AppIcons.check())
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self.btn_save)

        main_layout.addLayout(btn_layout)

    def _toggle_password_visibility(self) -> None:
        if self.txt_password.echoMode() == QLineEdit.EchoMode.Password:
            self.txt_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_pwd.setText("Hide")
        else:
            self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_pwd.setText("Show")

    def _load_current_values(self) -> None:
        conn = getattr(self.client, "conn", None)
        if conn:
            self.txt_base_url.setText(conn.base_url or "")
            self.txt_username.setText(conn.username or "")
            self.txt_password.setText(conn.password or "")
            self.txt_api_token.setText(conn.api_token or "")

    def _build_connection_object(self) -> Any:
        try:
            from inventree_client import InventreeConnection
            return InventreeConnection(
                base_url=self.txt_base_url.text().strip(),
                username=self.txt_username.text().strip(),
                password=self.txt_password.text(),
                api_token=self.txt_api_token.text().strip(),
            )
        except ImportError:
            # Fallback simple object
            class TempConn:
                def __init__(self, base_url, username, password, api_token):
                    self.base_url = base_url
                    self.username = username
                    self.password = password
                    self.api_token = api_token
            return TempConn(
                self.txt_base_url.text().strip(),
                self.txt_username.text().strip(),
                self.txt_password.text(),
                self.txt_api_token.text().strip(),
            )

    def _on_test_connection(self) -> None:
        conn = self._build_connection_object()
        self.lbl_test_status.setText("<span style='color: #58a6ff;'>Testing connection...</span>")
        QApplication.processEvents()

        try:
            from inventree_client import test_connection
            ok, msg = test_connection(conn)
            if ok:
                self.lbl_test_status.setText(f"<span style='color: #40ff80; font-weight: bold;'>✓ {msg}</span>")
            else:
                self.lbl_test_status.setText(f"<span style='color: #ff5555; font-weight: bold;'>✕ {msg}</span>")
        except Exception as exc:
            self.lbl_test_status.setText(f"<span style='color: #ff5555;'>✕ Error: {exc}</span>")

    def _on_save_clicked(self) -> None:
        base_url = self.txt_base_url.text().strip()
        if not base_url:
            QMessageBox.warning(self, "Missing URL", "Please enter the InvenTree server base URL.")
            return

        conn = self._build_connection_object()
        try:
            from inventree_client import save_settings
            save_settings(conn)
            self.client.reload_settings()
            logger.info(f"Saved and reloaded InvenTree settings for {base_url}")
            self.accept()
        except Exception as exc:
            logger.error(f"Failed to save InvenTree settings: {exc}")
            QMessageBox.critical(self, "Error Saving Settings", f"Failed to write settings:\n{exc}")
