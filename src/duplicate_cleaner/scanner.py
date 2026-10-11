from __future__ import annotations

import fnmatch
import os
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from duplicate_cleaner.config import ScanOptions, default_exclude_names
from duplicate_cleaner.hasher import hash_file
from duplicate_cleaner.models import DuplicateGroup, FileRecord, ScanResult

ProgressCallback = Callable[[str, int, int], None]


class ScanError(Exception):
    """Error controlado durante el escaneo."""


def _should_skip_dir(name: str, excluded_names: set[str]) -> bool:
    return name in excluded_names or name.startswith(".")


def _matches_exclude_glob(path: Path, exclude_globs: list[str]) -> bool:
    path_text = path.as_posix()
    for pattern in exclude_globs:
        if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(path_text, pattern):
            return True
    return False


def iter_files(
    options: ScanOptions,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[FileRecord], int, int]:
    excluded_names = default_exclude_names() | options.exclude_names
    records: list[FileRecord] = []
    skipped = 0
    total_bytes = 0

    for root in options.roots:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=options.follow_symlinks):
            current_dir = Path(dirpath)
            dirnames[:] = [
                name
                for name in dirnames
                if not _should_skip_dir(name, excluded_names)
                and not _matches_exclude_glob(current_dir / name, options.exclude_globs)
            ]

            for filename in filenames:
                file_path = current_dir / filename
                if _matches_exclude_glob(file_path, options.exclude_globs):
                    skipped += 1
                    continue

                try:
                    if not file_path.is_file():
                        skipped += 1
                        continue
                    stat = file_path.stat()
                except OSError:
                    skipped += 1
                    continue

                if stat.st_size < options.min_size:
                    skipped += 1
                    continue

                records.append(FileRecord(path=file_path, size=stat.st_size))
                total_bytes += stat.st_size
                if on_progress:
                    on_progress("discover", len(records), 0)

    return records, skipped, total_bytes


def find_duplicates(
    options: ScanOptions,
    on_progress: ProgressCallback | None = None,
) -> ScanResult:
    records, skipped, total_bytes = iter_files(options, on_progress=on_progress)
    by_size: dict[int, list[FileRecord]] = defaultdict(list)

    for record in records:
        by_size[record.size].append(record)

    duplicate_groups: list[DuplicateGroup] = []
    candidates = [records for records in by_size.values() if len(records) >= 2]
    hash_total = sum(len(records) for records in candidates)
    hash_done = 0

    for sized_records in candidates:
        size = sized_records[0].size
        by_digest: dict[str, list[FileRecord]] = defaultdict(list)
        for record in sized_records:
            try:
                digest = hash_file(record.path, options.algorithm, options.chunk_size)
            except OSError:
                skipped += 1
                hash_done += 1
                if on_progress:
                    on_progress("hash", hash_done, hash_total)
                continue
            by_digest[digest].append(record)
            hash_done += 1
            if on_progress:
                on_progress("hash", hash_done, hash_total)

        for digest, files in by_digest.items():
            if len(files) < 2:
                continue
            duplicate_groups.append(
                DuplicateGroup(
                    digest=digest,
                    size=size,
                    files=sorted(files, key=lambda item: str(item.path)),
                )
            )

    duplicate_groups.sort(key=lambda group: group.wasted_bytes, reverse=True)

    return ScanResult(
        roots=options.roots,
        duplicate_groups=duplicate_groups,
        scanned_files=len(records),
        skipped_files=skipped,
        total_bytes_scanned=total_bytes,
    )
