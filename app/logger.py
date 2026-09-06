# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import sys
import logging
import traceback
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import qInstallMessageHandler, QtMsgType
from .config import BASE_DIR

LOG_FILE = BASE_DIR / "app.log"

class SafeStreamWriter:
    """Safely writes console outputs to file without recursive logging traps."""

    def __init__(self, original_stream, prefix: str, log_path: Path):
        self.original_stream = original_stream
        self.prefix = prefix
        self.log_path = log_path
        self._in_write = False

    def write(self, buf: str):
        # 1. Output to actual console
        if self.original_stream is not None:
            try:
                self.original_stream.write(buf)
                self.original_stream.flush()
            except Exception:
                pass

        # 2. Append to log file directly if not empty and not recursive
        if self._in_write or not buf.strip():
            return

        self._in_write = True
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            lines = buf.splitlines()
            formatted = "\n".join(f"{now} [RAW-{self.prefix}]: {line}" for line in lines if line.strip())
            if formatted:
                with open(self.log_path, "a", encoding="utf-8", errors="replace") as f:
                    f.write(formatted + "\n")
        except Exception:
            pass
        finally:
            self._in_write = False

    def flush(self):
        if self.original_stream is not None:
            try:
                self.original_stream.flush()
            except Exception:
                pass

def qt_message_handler(mode: QtMsgType, context, message: str) -> None:
    # Ignore harmless font warnings
    if "Cannot find font directory" in message or "propagateSizeHints" in message:
        return

    logger = logging.getLogger("Qt")
    msg = f"{message} (File: {context.file}, Line: {context.line})" if context.file else message
    if mode == QtMsgType.QtDebugMsg:
        logger.debug(msg)
    elif mode == QtMsgType.QtInfoMsg:
        logger.info(msg)
    elif mode == QtMsgType.QtWarningMsg:
        logger.warning(msg)
    elif mode == QtMsgType.QtCriticalMsg:
        logger.error(msg)
    elif mode == QtMsgType.QtFatalMsg:
        logger.critical(msg)

def unhandled_exception_handler(exc_type, exc_value, exc_traceback) -> None:
    """Log uncaught exceptions to app.log with full traceback."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger = logging.getLogger("CRASH")
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger.critical(f"UNHANDLED EXCEPTION:\n{err_msg}")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n{'='*50}\n{now} [CRASH - UNHANDLED EXCEPTION]\n{err_msg}\n{'='*50}\n")
    except Exception:
        pass

def setup_logging() -> Path:
    """Initialize file and console logging."""
    # Ensure UTF-8 console output for symbols (like \u03a9) and Persian text
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File Handler (UTF-8)
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8", errors="replace")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console Handler (UTF-8 safe, if console is available)
    if sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # Safe Stream redirection for print() and external libraries
    sys.stdout = SafeStreamWriter(sys.__stdout__, "OUT", LOG_FILE)
    sys.stderr = SafeStreamWriter(sys.__stderr__, "ERR", LOG_FILE)

    # Register Exception & Qt Handlers
    sys.excepthook = unhandled_exception_handler
    qInstallMessageHandler(qt_message_handler)

    logging.info("=" * 60)
    logging.info("Altium DbLib Manager Logging initialized")
    logging.info(f"Log file: {LOG_FILE}")
    logging.info("=" * 60)

    return LOG_FILE
