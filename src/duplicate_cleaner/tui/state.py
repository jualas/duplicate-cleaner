from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from duplicate_cleaner.models import DuplicateGroup, ScanResult
from duplicate_cleaner.reporting import choose_files_to_delete, format_bytes


@dataclass
class FileSelectionState:
    marked: set[Path] = field(default_factory=set)

    def clear(self) -> None:
        self.marked.clear()

    def toggle(self, path: Path) -> None:
        if path in self.marked:
            self.marked.remove(path)
        else:
            self.marked.add(path)

    def is_marked(self, path: Path) -> bool:
        return path in self.marked

    def apply_keep_strategy(self, result: ScanResult, keep: str) -> None:
        self.marked = set(choose_files_to_delete(result, keep))

    def marked_size(self) -> int:
        total = 0
        for path in self.marked:
            if not path.exists():
                continue
            try:
                total += path.stat().st_size
            except OSError:
                continue
        return total

    def delete_marked(self) -> tuple[int, int]:
        deleted = 0
        errors = 0
        for path in list(self.marked):
            if not path.exists():
                self.marked.discard(path)
                continue
            try:
                path.unlink()
                deleted += 1
                self.marked.discard(path)
            except OSError:
                errors += 1
        return deleted, errors


def group_label(index: int, group: DuplicateGroup) -> str:
    return (
        f"Grupo {index} · {len(group.files)} archivos · "
        f"{format_bytes(group.wasted_bytes)} recuperables"
    )
