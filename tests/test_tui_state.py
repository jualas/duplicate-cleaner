from __future__ import annotations

from pathlib import Path

from duplicate_cleaner.config import ScanOptions
from duplicate_cleaner.scanner import find_duplicates
from duplicate_cleaner.tui.state import FileSelectionState, group_label


def write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_selection_toggle_and_keep_strategy(tmp_path: Path) -> None:
    content = b"duplicado tui"
    write_file(tmp_path / "a.txt", content)
    write_file(tmp_path / "b.txt", content)

    result = find_duplicates(ScanOptions(roots=[tmp_path]))
    state = FileSelectionState()

    state.apply_keep_strategy(result, "oldest")
    assert len(state.marked) == 1

    path = next(iter(state.marked))
    state.toggle(path)
    assert path not in state.marked

    state.toggle(path)
    assert path in state.marked


def test_delete_marked_removes_files(tmp_path: Path) -> None:
    content = b"borrar"
    path_a = tmp_path / "a.txt"
    path_b = tmp_path / "b.txt"
    write_file(path_a, content)
    write_file(path_b, content)

    result = find_duplicates(ScanOptions(roots=[tmp_path]))
    state = FileSelectionState()
    state.apply_keep_strategy(result, "oldest")

    deleted, errors = state.delete_marked()
    assert deleted == 1
    assert errors == 0
    assert len(state.marked) == 0
    remaining = [path for path in (path_a, path_b) if path.exists()]
    assert len(remaining) == 1


def test_group_label_contains_file_count(tmp_path: Path) -> None:
    content = b"x"
    write_file(tmp_path / "1.txt", content)
    write_file(tmp_path / "2.txt", content)

    result = find_duplicates(ScanOptions(roots=[tmp_path]))
    label = group_label(1, result.duplicate_groups[0])
    assert "2 archivos" in label
