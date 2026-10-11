from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from duplicate_cleaner.gui.main_window import create_main_window


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Duplicate Cleaner")
    app.setOrganizationName("DuplicateCleaner")
    window = create_main_window()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
