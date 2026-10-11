from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from duplicate_cleaner.models import ScanResult


def format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.2f} {unit}"
        amount /= 1024
    return f"{value} B"


def render_scan_result(result: ScanResult, console: Console) -> None:
    console.print(
        f"[bold]Archivos analizados:[/bold] {result.scanned_files} "
        f"([dim]{format_bytes(result.total_bytes_scanned)}[/dim])"
    )
    console.print(f"[bold]Omitidos:[/bold] {result.skipped_files}")
    console.print(
        f"[bold]Grupos duplicados:[/bold] {len(result.duplicate_groups)} "
        f"([yellow]{format_bytes(result.wasted_bytes)} recuperables[/yellow])"
    )

    if not result.duplicate_groups:
        console.print("[green]No se encontraron duplicados.[/green]")
        return

    for index, group in enumerate(result.duplicate_groups, start=1):
        console.print()
        console.print(
            f"[bold cyan]Grupo {index}[/bold cyan] "
            f"({len(group.files)} archivos, {format_bytes(group.size)} c/u, "
            f"desperdicio {format_bytes(group.wasted_bytes)})"
        )
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", justify="right")
        table.add_column("Ruta")
        for file_index, record in enumerate(group.files, start=1):
            table.add_row(str(file_index), str(record.path))
        console.print(table)


def render_scan_result_json(result: ScanResult) -> str:
    payload = {
        "roots": [str(path) for path in result.roots],
        "scanned_files": result.scanned_files,
        "skipped_files": result.skipped_files,
        "total_bytes_scanned": result.total_bytes_scanned,
        "wasted_bytes": result.wasted_bytes,
        "duplicate_groups": [
            {
                "digest": group.digest,
                "size": group.size,
                "wasted_bytes": group.wasted_bytes,
                "files": [str(record.path) for record in group.files],
            }
            for group in result.duplicate_groups
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def choose_files_to_delete(
    result: ScanResult,
    keep: str,
) -> list[Path]:
    selected: list[Path] = []
    for group in result.duplicate_groups:
        files = list(group.files)
        if keep == "newest":
            files.sort(key=lambda item: item.path.stat().st_mtime, reverse=True)
        elif keep == "oldest":
            files.sort(key=lambda item: item.path.stat().st_mtime)
        else:
            files.sort(key=lambda item: str(item.path))
        selected.extend(record.path for record in files[1:])
    return selected


def delete_files(
    paths: list[Path],
    *,
    dry_run: bool,
    console: Console,
) -> tuple[int, int]:
    freed = sum(path.stat().st_size for path in paths if path.exists())
    mode = "Simulación" if dry_run else "Eliminación"
    console.print(
        f"[bold]{mode}:[/bold] {len(paths)} archivos "
        f"({format_bytes(freed)} liberables)"
    )

    deleted = 0
    errors = 0
    for path in paths:
        if dry_run:
            console.print(f"[dim]DRY-RUN[/dim] {path}")
            continue
        try:
            path.unlink()
            deleted += 1
            console.print(f"[green]Eliminado[/green] {path}")
        except OSError as exc:
            errors += 1
            console.print(f"[red]No se pudo eliminar[/red] {path}: {exc}")

    if not dry_run:
        console.print(f"[bold]Completado:[/bold] {deleted} eliminados, {errors} errores.")

    return deleted, errors
