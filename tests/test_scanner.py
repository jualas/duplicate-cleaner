from __future__ import annotations

from pathlib import Path

from duplicate_cleaner.config import ScanOptions
from duplicate_cleaner.report_io import load_report, save_report
from duplicate_cleaner.reporting import choose_files_to_delete
from duplicate_cleaner.scanner import find_duplicates


def write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_find_duplicates_groups_identical_files(tmp_path: Path) -> None:
    content = b"contenido duplicado para prueba"
    write_file(tmp_path / "a" / "file1.txt", content)
    write_file(tmp_path / "b" / "file2.txt", content)
    write_file(tmp_path / "c" / "unique.txt", b"unico")

    result = find_duplicates(ScanOptions(roots=[tmp_path]))

    assert result.scanned_files == 3
    assert len(result.duplicate_groups) == 1
    assert len(result.duplicate_groups[0].files) == 2
    assert result.wasted_bytes == len(content)


def test_respects_min_size(tmp_path: Path) -> None:
    write_file(tmp_path / "small1.txt", b"x")
    write_file(tmp_path / "small2.txt", b"x")

    result = find_duplicates(ScanOptions(roots=[tmp_path], min_size=10))

    assert result.scanned_files == 0
    assert result.duplicate_groups == []


def test_progress_callback_reports_phases(tmp_path: Path) -> None:
    content = b"duplicado"
    write_file(tmp_path / "a.txt", content)
    write_file(tmp_path / "b.txt", content)
    events: list[tuple[str, int, int]] = []

    find_duplicates(
        ScanOptions(roots=[tmp_path]),
        on_progress=lambda phase, current, total: events.append((phase, current, total)),
    )

    assert any(event[0] == "discover" for event in events)
    assert any(event[0] == "hash" for event in events)


def test_save_and_load_report_roundtrip(tmp_path: Path) -> None:
    content = b"mismo contenido"
    write_file(tmp_path / "x.txt", content)
    write_file(tmp_path / "y.txt", content)

    original = find_duplicates(ScanOptions(roots=[tmp_path]))
    report_path = tmp_path / "informe.json"
    save_report(original, report_path)

    loaded = load_report(report_path)

    assert loaded.scanned_files == original.scanned_files
    assert len(loaded.duplicate_groups) == 1
    assert len(loaded.duplicate_groups[0].files) == 2


def test_choose_files_to_delete_keeps_oldest(tmp_path: Path) -> None:
    content = b"dup"
    path_a = tmp_path / "a.txt"
    path_b = tmp_path / "b.txt"
    write_file(path_a, content)
    write_file(path_b, content)

    result = find_duplicates(ScanOptions(roots=[tmp_path]))
    targets = choose_files_to_delete(result, "oldest")

    assert len(targets) == 1
    assert targets[0] != min(path_a, path_b, key=lambda p: p.stat().st_mtime)
