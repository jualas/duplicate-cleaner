from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_EXCLUDES_WINDOWS = {
    "System Volume Information",
    "$Recycle.Bin",
    "Recovery",
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "ProgramData",
}

DEFAULT_EXCLUDES_LINUX = {
    "proc",
    "sys",
    "dev",
    "run",
    "snap",
    "lost+found",
}


@dataclass(slots=True)
class ScanOptions:
    roots: list[Path]
    min_size: int = 1
    algorithm: str = "sha256"
    follow_symlinks: bool = False
    exclude_names: set[str] = field(default_factory=set)
    exclude_globs: list[str] = field(default_factory=list)
    chunk_size: int = 1024 * 1024


def default_exclude_names() -> set[str]:
    if sys.platform.startswith("win"):
        return set(DEFAULT_EXCLUDES_WINDOWS)
    return set(DEFAULT_EXCLUDES_LINUX)


def normalize_roots(roots: list[str | Path]) -> list[Path]:
    normalized: list[Path] = []
    for root in roots:
        path = Path(root).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"No existe la ruta: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"No es un directorio: {path}")
        normalized.append(path)
    return normalized
