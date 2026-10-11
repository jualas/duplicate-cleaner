from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from duplicate_cleaner.config import ScanOptions, normalize_roots
from duplicate_cleaner.report_io import ReportError, load_report, save_report
from duplicate_cleaner.reporting import (
    choose_files_to_delete,
    delete_files,
    format_bytes,
    render_scan_result,
    render_scan_result_json,
)
from duplicate_cleaner.scanner import ScanError, find_duplicates

app = typer.Typer(
    help="Duplicate Cleaner: detecta y elimina archivos duplicados en Windows y Linux.",
    no_args_is_help=True,
)
console = Console()


class KeepStrategy(str, Enum):
    oldest = "oldest"
    newest = "newest"
    first = "first"


def _build_options(
    paths: list[Path],
    min_size: int,
    algorithm: str,
    follow_symlinks: bool,
    exclude_name: list[str],
    exclude_glob: list[str],
) -> ScanOptions:
    return ScanOptions(
        roots=paths,
        min_size=min_size,
        algorithm=algorithm,
        follow_symlinks=follow_symlinks,
        exclude_names=set(exclude_name),
        exclude_globs=list(exclude_glob),
    )


@app.command("scan")
def scan_command(
    paths: Annotated[
        list[Path],
        typer.Argument(help="Directorios a analizar (puede indicar varios)."),
    ],
    min_size: Annotated[
        int,
        typer.Option("--min-size", help="Tamaño mínimo en bytes para considerar un archivo."),
    ] = 1,
    algorithm: Annotated[
        str,
        typer.Option("--algorithm", help="Algoritmo de hash: sha256, md5, sha1."),
    ] = "sha256",
    follow_symlinks: Annotated[
        bool,
        typer.Option("--follow-symlinks", help="Seguir enlaces simbólicos."),
    ] = False,
    exclude_name: Annotated[
        list[str],
        typer.Option("--exclude-name", help="Nombre de carpeta a omitir."),
    ] = [],
    exclude_glob: Annotated[
        list[str],
        typer.Option("--exclude-glob", help="Patrón glob para omitir rutas."),
    ] = [],
    output: Annotated[
        str,
        typer.Option("--output", help="Formato de salida: table o json."),
    ] = "table",
    save: Annotated[
        Path | None,
        typer.Option("--save", help="Guardar informe reutilizable en JSON."),
    ] = None,
) -> None:
    """Busca archivos duplicados por tamaño y hash."""
    try:
        roots = normalize_roots(paths)
        options = _build_options(
            roots,
            min_size,
            algorithm,
            follow_symlinks,
            exclude_name,
            exclude_glob,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task("Escaneando archivos...", total=None)
        try:
            result = find_duplicates(options)
        except ScanError as exc:
            console.print(f"[red]Error de escaneo:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    if save is not None:
        save_report(result, save, algorithm=algorithm)
        console.print(f"[green]Informe guardado:[/green] {save}")

    if output == "json":
        console.print(render_scan_result_json(result))
        return

    if save is None or output == "table":
        render_scan_result(result, console)


@app.command("clean")
def clean_command(
    paths: Annotated[
        list[Path],
        typer.Argument(help="Directorios a analizar antes de limpiar."),
    ],
    keep: Annotated[
        KeepStrategy,
        typer.Option("--keep", help="Qué copia conservar en cada grupo."),
    ] = KeepStrategy.oldest,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--apply", help="Simular sin borrar archivos."),
    ] = True,
    min_size: Annotated[int, typer.Option("--min-size")] = 1,
    algorithm: Annotated[str, typer.Option("--algorithm")] = "sha256",
    follow_symlinks: Annotated[bool, typer.Option("--follow-symlinks")] = False,
    exclude_name: Annotated[list[str], typer.Option("--exclude-name")] = [],
    exclude_glob: Annotated[list[str], typer.Option("--exclude-glob")] = [],
) -> None:
    """Elimina duplicados conservando una copia por grupo (re-escanea)."""
    try:
        roots = normalize_roots(paths)
        options = _build_options(
            roots,
            min_size,
            algorithm,
            follow_symlinks,
            exclude_name,
            exclude_glob,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task("Analizando duplicados...", total=None)
        result = find_duplicates(options)

    targets = choose_files_to_delete(result, keep.value)
    if not targets:
        console.print("[green]No hay duplicados para eliminar.[/green]")
        return

    freed = sum(p.stat().st_size for p in targets if p.exists())
    console.print(
        f"[bold]Estrategia:[/bold] conservar '{keep.value}' "
        f"({format_bytes(freed)} liberables)"
    )
    delete_files(targets, dry_run=dry_run, console=console)


@app.command("clean-report")
def clean_report_command(
    report: Annotated[
        Path,
        typer.Argument(help="Informe JSON generado con scan --save."),
    ],
    keep: Annotated[
        KeepStrategy,
        typer.Option("--keep", help="Qué copia conservar en cada grupo."),
    ] = KeepStrategy.oldest,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--apply", help="Simular sin borrar archivos."),
    ] = True,
) -> None:
    """Elimina duplicados desde un informe guardado, sin re-escanear."""
    try:
        result = load_report(report)
    except ReportError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    targets = choose_files_to_delete(result, keep.value)
    if not targets:
        console.print("[green]No hay duplicados para eliminar.[/green]")
        return

    console.print(
        f"[bold]Informe:[/bold] {report} · "
        f"[bold]Grupos:[/bold] {len(result.duplicate_groups)} · "
        f"[bold]Estrategia:[/bold] conservar '{keep.value}'"
    )
    delete_files(targets, dry_run=dry_run, console=console)


@app.command("gui")
def gui_command() -> None:
    """Abre la interfaz gráfica para revisar y eliminar duplicados."""
    try:
        from duplicate_cleaner.gui.app import main as gui_main
    except ImportError as exc:
        console.print('[red]Falta PySide6.[/red] Instala con: pip install -e ".[gui]"')
        raise typer.Exit(code=1) from exc
    gui_main()


@app.command("tui")
def tui_command(
    paths: Annotated[
        list[Path],
        typer.Argument(help="Directorios a analizar (opcional si usas --report)."),
    ] = [],
    report: Annotated[
        Path | None,
        typer.Option("--report", help="Informe JSON generado con scan --save."),
    ] = None,
    min_size: Annotated[int, typer.Option("--min-size")] = 1,
    algorithm: Annotated[str, typer.Option("--algorithm")] = "sha256",
) -> None:
    """Interfaz de terminal interactiva (ideal para SSH sin escritorio)."""
    if not paths and report is None:
        console.print("[red]Indica rutas a escanear o --report informe.json[/red]")
        raise typer.Exit(code=1)
    try:
        from duplicate_cleaner.tui.app import main as tui_main
    except ImportError as exc:
        console.print('[red]Falta Textual.[/red] Instala con: pip install -e ".[tui]"')
        raise typer.Exit(code=1) from exc
    tui_main(paths=paths or None, report=report, min_size=min_size, algorithm=algorithm)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
