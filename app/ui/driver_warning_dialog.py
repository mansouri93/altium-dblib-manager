# -*- coding: utf-8 -*-
from __future__ import annotations
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFrame,
)
from .icons import AppIcons

class AccessDriverWarningDialog(QDialog):
    """
    Warning dialog shown when the Microsoft Access ODBC Driver is not installed.
    Provides direct download links and clear installation instructions.
    """

    DOWNLOAD_URL = "https://www.microsoft.com/en-us/download/details.aspx?id=54920"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Microsoft Access Database Driver Required")
        self.resize(560, 290)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header with icon and title
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(AppIcons.warning().pixmap(36, 36))
        header_layout.addWidget(icon_lbl)

        title_layout = QVBoxLayout()
        title_lbl = QLabel("Microsoft Access Driver Missing")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffb86c;")
        desc_lbl = QLabel(
            "The <b>Microsoft Access Driver (*.mdb, *.accdb)</b> is not detected on this system.\n"
            "This driver is required to open, read, edit, and create Access database (.accdb) files."
        )
        desc_lbl.setStyleSheet("color: #cccccc; font-size: 12px; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        title_layout.addWidget(title_lbl)
        title_layout.addWidget(desc_lbl)
        header_layout.addLayout(title_layout, stretch=1)
        layout.addLayout(header_layout)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #33334d;")
        layout.addWidget(line)

        # Instructions
        inst_lbl = QLabel(
            "Please download and install <b>Microsoft Access Database Engine 2016 Redistributable</b> "
            "(select <b>accessdatabaseengine_X64.exe</b> for 64-bit Python):"
        )
        inst_lbl.setWordWrap(True)
        inst_lbl.setStyleSheet("color: #e0e0f0; font-size: 12px;")
        layout.addWidget(inst_lbl)

        # Download URL display box
        url_box = QLineEdit(self.DOWNLOAD_URL)
        url_box.setReadOnly(True)
        url_box.setStyleSheet("background-color: #1a1a28; color: #79c0ff; padding: 4px 8px; border: 1px solid #3d3d5c;")
        layout.addWidget(url_box)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_download = QPushButton(" Open Download Page in Browser")
        btn_download.setObjectName("PrimaryButton")
        btn_download.setIcon(AppIcons.link())
        btn_download.clicked.connect(self._open_download_url)
        btn_layout.addWidget(btn_download)

        btn_layout.addStretch()

        btn_close = QPushButton("Dismiss")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _open_download_url(self) -> None:
        QDesktopServices.openUrl(QUrl(self.DOWNLOAD_URL))
