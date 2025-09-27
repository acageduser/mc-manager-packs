# app/main.py
from __future__ import annotations

import os
import sys


def _prepare_sys_path() -> None:
    """
    Ensure 'app' package is importable in both source and PyInstaller onefile runs.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller onefile extracts to a temp dir exposed as _MEIPASS.
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and meipass not in sys.path:
            sys.path.insert(0, meipass)
    else:
        # Running from source: add repo root so 'import app....' resolves.
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)


def _resolve_main_window():
    """
    Import the MainWindow class. We try the normal absolute import first.
    The relative import is a lightweight fallback for unusual layouts.
    """
    _prepare_sys_path()
    try:
        from app.ui.main_window import MainWindow  # type: ignore
        return MainWindow
    except ModuleNotFoundError:
        # Fallback: allow running as a package module (python -m app.main)
        from ui.main_window import MainWindow  # type: ignore
        return MainWindow


def main() -> None:
    MainWindow = _resolve_main_window()

    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
