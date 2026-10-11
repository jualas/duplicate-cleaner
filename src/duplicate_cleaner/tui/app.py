from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Label, ListItem, ListView, Static

from duplicate_cleaner.config import ScanOptions, normalize_roots
from duplicate_cleaner.models import ScanResult
from duplicate_cleaner.report_io import load_report
from duplicate_cleaner.reporting import format_bytes
from duplicate_cleaner.scanner import find_duplicates
from duplicate_cleaner.tui.state import FileSelectionState, group_label

KEEP_STRATEGIES = ("oldest", "newest", "first")


class ConfirmDeleteScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmDeleteScreen {
        align: center middle;
    }
    #confirm-box {
        width: 60;
        height: auto;
        padding: 1 2;
        border: thick $warning;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("y", "confirm", "Sí"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "No"),
    ]

    def __init__(self, count: int, total_bytes: int) -> None:
        super().__init__()
        self._count = count
        self._total_bytes = total_bytes

    def compose(self) -> ComposeResult:
        yield Static(
            f"¿Eliminar {self._count} archivos ({format_bytes(self._total_bytes)})?\n"
            "Esta acción no se puede deshacer.\n\n[y] Sí   [n] No",
            id="confirm-box",
        )

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class DuplicateCleanerTui(App):
    CSS = """
    #main {
        height: 1fr;
    }
    #groups-panel {
        width: 35%;
        border-right: solid $primary;
    }
    #files-panel {
        width: 1fr;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    ListView:focus ListItem.-highlight {
        background: $accent;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Salir"),
        Binding("k", "apply_keep", "Estrategia"),
        Binding("d", "delete_marked", "Eliminar"),
        Binding("a", "toggle_all_in_group", "Alternar grupo"),
        Binding("space", "toggle_file", "Marcar"),
    ]

    def __init__(
        self,
        *,
        roots: list[Path] | None = None,
        report: Path | None = None,
        min_size: int = 1,
        algorithm: str = "sha256",
    ) -> None:
        super().__init__()
        self._roots = roots or []
        self._report = report
        self._min_size = min_size
        self._algorithm = algorithm
        self._result: ScanResult | None = None
        self._selection = FileSelectionState()
        self._keep_index = 0
        self._active_group = 0
        self._base_status = "Listo."

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="groups-panel"):
                yield Label("Grupos duplicados", id="groups-title")
                yield ListView(id="groups")
            with Vertical(id="files-panel"):
                yield Label("Archivos del grupo", id="files-title")
                yield DataTable(id="files", cursor_type="row")
        yield Static("Listo.", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#files", DataTable)
        table.add_columns("Eliminar", "Ruta", "Tamaño", "Modificado")
        if self._report is not None:
            self._load_report(self._report)
        elif self._roots:
            self._start_scan()
        else:
            self._set_status("Indica rutas o --report informe.json")

    def _set_status(self, message: str, *, remember: bool = False) -> None:
        if remember:
            self._base_status = message
        self.query_one("#status-bar", Static).update(message)

    def _load_report(self, path: Path) -> None:
        try:
            self._result = load_report(path)
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Error al cargar informe: {exc}")
            return
        self._populate_groups()
        self._apply_current_keep()
        self._set_status(
            f"Informe: {path} · {len(self._result.duplicate_groups)} grupos · "
            f"{format_bytes(self._result.wasted_bytes)} recuperables",
            remember=True,
        )

    def _start_scan(self) -> None:
        try:
            roots = normalize_roots(self._roots)
            options = ScanOptions(
                roots=roots,
                min_size=self._min_size,
                algorithm=self._algorithm,
            )
        except (FileNotFoundError, NotADirectoryError) as exc:
            self._set_status(f"Error: {exc}")
            return
        self._set_status("Escaneando...", remember=True)
        self.run_scan_worker(options)

    @work(thread=True, exclusive=True)
    def run_scan_worker(self, options: ScanOptions) -> None:
        def on_progress(phase: str, current: int, total: int) -> None:
            if phase == "discover":
                self.call_from_thread(self._set_status, f"Descubriendo archivos… {current}")
            elif total > 0:
                self.call_from_thread(
                    self._set_status,
                    f"Calculando hashes… {current}/{total}",
                )

        result = find_duplicates(options, on_progress=on_progress)
        self.call_from_thread(self._on_scan_finished, result)

    def _on_scan_finished(self, result: ScanResult) -> None:
        self._result = result
        self._populate_groups()
        self._apply_current_keep()
        self._set_status(
            f"Escaneo completado · {result.scanned_files} archivos · "
            f"{len(result.duplicate_groups)} grupos · "
            f"{format_bytes(result.wasted_bytes)} recuperables",
            remember=True,
        )

    def _populate_groups(self) -> None:
        groups = self.query_one("#groups", ListView)
        groups.clear()
        if not self._result:
            return
        for index, group in enumerate(self._result.duplicate_groups, start=1):
            groups.append(ListItem(Label(group_label(index, group)), id=f"group-{index - 1}"))
        if self._result.duplicate_groups:
            groups.index = 0
            self._show_group(0)

    def _show_group(self, group_index: int) -> None:
        if not self._result or group_index >= len(self._result.duplicate_groups):
            return
        self._active_group = group_index
        group = self._result.duplicate_groups[group_index]
        table = self.query_one("#files", DataTable)
        table.clear()
        for record in group.files:
            marked = "✓" if self._selection.is_marked(record.path) else " "
            modified = self._format_mtime(record.path)
            table.add_row(marked, str(record.path), format_bytes(record.size), modified)
        self._refresh_selection_status()

    @staticmethod
    def _format_mtime(path: Path) -> str:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            return "—"

    def _refresh_selection_status(self) -> None:
        count = len(self._selection.marked)
        size = self._selection.marked_size()
        keep = KEEP_STRATEGIES[self._keep_index]
        self._set_status(
            f"{self._base_status} · Seleccionados: {count} ({format_bytes(size)}) · "
            f"Estrategia: {keep} [k]"
        )

    @on(ListView.Selected, "#groups")
    def on_group_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "groups":
            return
        self._show_group(event.list_view.index or 0)

    def action_toggle_file(self) -> None:
        if not self._result:
            return
        table = self.query_one("#files", DataTable)
        if table.cursor_row is None:
            return
        group = self._result.duplicate_groups[self._active_group]
        row = table.cursor_row
        if row >= len(group.files):
            return
        path = group.files[row].path
        self._selection.toggle(path)
        self._show_group(self._active_group)

    def action_toggle_all_in_group(self) -> None:
        if not self._result:
            return
        group = self._result.duplicate_groups[self._active_group]
        paths = [record.path for record in group.files]
        if all(self._selection.is_marked(path) for path in paths):
            for path in paths:
                self._selection.marked.discard(path)
        else:
            for path in paths:
                self._selection.marked.add(path)
        self._show_group(self._active_group)

    def _apply_current_keep(self) -> None:
        if not self._result:
            return
        keep = KEEP_STRATEGIES[self._keep_index]
        self._selection.apply_keep_strategy(self._result, keep)
        self._show_group(self._active_group)

    def action_apply_keep(self) -> None:
        self._keep_index = (self._keep_index + 1) % len(KEEP_STRATEGIES)
        self._apply_current_keep()

    def action_delete_marked(self) -> None:
        if not self._selection.marked:
            self._set_status(f"{self._base_status} · No hay archivos marcados.")
            return

        count = len(self._selection.marked)
        total = self._selection.marked_size()

        def on_confirm(confirmed: bool | None) -> None:
            if not confirmed:
                self._refresh_selection_status()
                return
            deleted, errors = self._selection.delete_marked()
            self._refresh_after_delete()
            self._set_status(
                f"{self._base_status} · Eliminados: {deleted} · Errores: {errors}",
                remember=True,
            )

        self.push_screen(ConfirmDeleteScreen(count, total), on_confirm)

    def _refresh_after_delete(self) -> None:
        if not self._result:
            return
        for group in self._result.duplicate_groups:
            group.files = [record for record in group.files if record.path.exists()]
        self._result.duplicate_groups = [
            group for group in self._result.duplicate_groups if len(group.files) >= 2
        ]
        self._populate_groups()


def main(
    paths: list[Path] | None = None,
    report: Path | None = None,
    min_size: int = 1,
    algorithm: str = "sha256",
) -> None:
    app = DuplicateCleanerTui(
        roots=paths,
        report=report,
        min_size=min_size,
        algorithm=algorithm,
    )
    app.run()


if __name__ == "__main__":
    main()
