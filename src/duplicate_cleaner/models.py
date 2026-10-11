from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class FileRecord:
    path: Path
    size: int


@dataclass(slots=True)
class DuplicateGroup:
    digest: str
    size: int
    files: list[FileRecord] = field(default_factory=list)

    @property
    def wasted_bytes(self) -> int:
        if len(self.files) <= 1:
            return 0
        return self.size * (len(self.files) - 1)


@dataclass(slots=True)
class ScanResult:
    roots: list[Path]
    duplicate_groups: list[DuplicateGroup]
    scanned_files: int
    skipped_files: int
    total_bytes_scanned: int

    @property
    def duplicate_file_count(self) -> int:
        return sum(len(group.files) for group in self.duplicate_groups)

    @property
    def wasted_bytes(self) -> int:
        return sum(group.wasted_bytes for group in self.duplicate_groups)
