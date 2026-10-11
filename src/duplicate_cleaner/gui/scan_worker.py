from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from duplicate_cleaner.config import ScanOptions
from duplicate_cleaner.scanner import find_duplicates


class ScanWorker(QThread):
    progress = Signal(str, int, int)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, options: ScanOptions) -> None:
        super().__init__()
        self._options = options

    def run(self) -> None:
        try:
            result = find_duplicates(
                self._options,
                on_progress=lambda phase, current, total: self.progress.emit(phase, current, total),
            )
        except Exception as exc:  # noqa: BLE001 - mostrar error genérico en la GUI
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(result)
