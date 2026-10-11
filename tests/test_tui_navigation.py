from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.widgets import DataTable

from duplicate_cleaner.tui.app import DuplicateCleanerTui


def write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_arrow_keys_update_files_panel(tmp_path: Path) -> None:
    write_file(tmp_path / "a1.txt", b"grupo a")
    write_file(tmp_path / "a2.txt", b"grupo a")
    write_file(tmp_path / "b1.bin", b"grupo b, otro contenido")
    write_file(tmp_path / "b2.bin", b"grupo b, otro contenido")
    write_file(tmp_path / "b3.bin", b"grupo b, otro contenido")

    async def run() -> tuple[int, int, int]:
        app = DuplicateCleanerTui(roots=[tmp_path])
        async with app.run_test() as pilot:
            for _ in range(50):
                await pilot.pause(0.05)
                if app._result is not None:
                    break
            await pilot.pause()
            app.query_one("#groups").focus()
            table = app.query_one("#files", DataTable)
            first = table.row_count
            await pilot.press("down")
            await pilot.pause()
            return first, table.row_count, app._active_group

    first, after_down, active = asyncio.run(run())
    assert active == 1
    assert {first, after_down} == {2, 3}
