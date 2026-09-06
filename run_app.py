# -*- coding: utf-8 -*-
"""
Main application launcher for Altium DbLib Manager.
"""
import sys
import os
import logging

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.logger import setup_logging

def main():
    # 1. Initialize logging to file and console
    log_path = setup_logging()
    logging.info("Starting Altium DbLib Manager...")

    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from app.ui.main_window import MainWindow
        from app.ui.styles import apply_theme
        from app.config import get_current_theme
        from app.ui.smooth_scroll import install_global_wheel_scroll_filter

        # Enable High DPI scaling
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        app = QApplication(sys.argv)
        app.setApplicationName("Altium DbLib Manager")
        app.setOrganizationName("Mansouri")
        
        # Load and apply configured UI theme
        saved_theme = get_current_theme()
        apply_theme(saved_theme, app)

        # Disable mouse wheel value changes on all input widgets (comboboxes, spinboxes, sliders)
        install_global_wheel_scroll_filter(app)

        window = MainWindow()
        window.show()

        logging.info("Entering Qt application event loop...")
        exit_code = app.exec()
        logging.info(f"Application exited normally with code {exit_code}")
        sys.exit(exit_code)
    except Exception as exc:
        logging.critical(f"Fatal error during application execution: {exc}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
