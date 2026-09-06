# -*- coding: utf-8 -*-
from __future__ import annotations
import qtawesome as qta
from PySide6.QtGui import QIcon

class AppIcons:
    """Central registry of modern vector icons for the application."""

    @staticmethod
    def zoom_in(color: str = "#d0d0e0") -> QIcon:
        return qta.icon("fa5s.search-plus", color=color)

    @staticmethod
    def zoom_out(color: str = "#d0d0e0") -> QIcon:
        return qta.icon("fa5s.search-minus", color=color)

    @staticmethod
    def zoom_reset(color: str = "#d0d0e0") -> QIcon:
        return qta.icon("fa5s.expand", color=color)

    @staticmethod
    def add(color: str = "#ffffff") -> QIcon:
        return qta.icon("fa5s.plus", color=color)

    @staticmethod
    def delete(color: str = "#ffffff") -> QIcon:
        return qta.icon("fa5s.trash-alt", color=color)

    @staticmethod
    def browse_symbol(color: str = "#58a6ff") -> QIcon:
        return qta.icon("fa5s.microchip", color=color)

    @staticmethod
    def browse_footprint(color: str = "#e3b341") -> QIcon:
        return qta.icon("fa5s.th-large", color=color)

    @staticmethod
    def sync_inventree(color: str = "#58a6ff") -> QIcon:
        return qta.icon("fa5s.sync-alt", color=color)

    @staticmethod
    def sync_bulk(color: str = "#ffffff") -> QIcon:
        return qta.icon("fa5s.cloud-download-alt", color=color)

    @staticmethod
    def refresh(color: str = "#d0d0e0") -> QIcon:
        return qta.icon("fa5s.redo-alt", color=color)

    @staticmethod
    def new_category(color: str = "#58a6ff") -> QIcon:
        return qta.icon("fa5s.folder-plus", color=color)

    @staticmethod
    def search(color: str = "#8b949e") -> QIcon:
        return qta.icon("fa5s.search", color=color)

    @staticmethod
    def link(color: str = "#ffffff") -> QIcon:
        return qta.icon("fa5s.link", color=color)

    @staticmethod
    def edit(color: str = "#c9d1d9") -> QIcon:
        return qta.icon("fa5s.edit", color=color)

    @staticmethod
    def check(color: str = "#ffffff") -> QIcon:
        return qta.icon("fa5s.check", color=color)

    @staticmethod
    def cancel(color: str = "#c9d1d9") -> QIcon:
        return qta.icon("fa5s.times", color=color)

    @staticmethod
    def inventory_box(color: str = "#58a6ff") -> QIcon:
        return qta.icon("fa5s.boxes", color=color)

    @staticmethod
    def table(color: str = "#d0d0e0") -> QIcon:
        return qta.icon("fa5s.table", color=color)

    @staticmethod
    def columns(color: str = "#d0d0e0") -> QIcon:
        return qta.icon("fa5s.columns", color=color)

    @staticmethod
    def unit_settings(color: str = "#58a6ff") -> QIcon:
        return qta.icon("fa5s.ruler-combined", color=color)

    @staticmethod
    def settings(color: str = "#d0d0e0") -> QIcon:
        return qta.icon("fa5s.cog", color=color)

    @staticmethod
    def history(color: str = "#e3b341") -> QIcon:
        return qta.icon("fa5s.history", color=color)

    @staticmethod
    def server(color: str = "#58a6ff") -> QIcon:
        return qta.icon("fa5s.server", color=color)

    @staticmethod
    def database(color: str = "#58a6ff") -> QIcon:
        return qta.icon("fa5s.database", color=color)

    @staticmethod
    def folder_open(color: str = "#e3b341") -> QIcon:
        return qta.icon("fa5s.folder-open", color=color)

    @staticmethod
    def warning(color: str = "#f0883e") -> QIcon:
        return qta.icon("fa5s.exclamation-triangle", color=color)

    @staticmethod
    def external_link(color: str = "#ffffff") -> QIcon:
        return qta.icon("fa5s.external-link-alt", color=color)

    @staticmethod
    def chevron_left(color: str = "#d0d0e0") -> QIcon:
        return qta.icon("fa5s.chevron-left", color=color)

    @staticmethod
    def chevron_right(color: str = "#d0d0e0") -> QIcon:
        return qta.icon("fa5s.chevron-right", color=color)

    @staticmethod
    def sidebar_left(color: str = "#d0d0e0") -> QIcon:
        return qta.icon("fa5s.bars", color=color)

    @staticmethod
    def sidebar_right(color: str = "#d0d0e0") -> QIcon:
        return qta.icon("fa5s.sliders-h", color=color)

    @staticmethod
    def palette(color: str = "#58a6ff") -> QIcon:
        return qta.icon("fa5s.palette", color=color)


