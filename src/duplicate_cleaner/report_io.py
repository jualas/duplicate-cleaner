from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from duplicate_cleaner.models import DuplicateGroup, FileRecord, ScanResult

REPORT_VERSION = 1


class ReportError(Exception):
    """Error al leer o escribir un informe de escaneo."""


def save_report(result: ScanResult, path: Path, algorithm: str = "sha256") -> None:
    payload = {
        "version": REPORT_VERSION,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "algorithm": algorithm,
        "roots": [str(root) for root in result.roots],
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_report(path: Path) -> ScanResult:
    if not path.exists():
        raise ReportError(f"No existe el informe: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"Informe inválido: {path}") from exc

    version = payload.get("version")
    if version != REPORT_VERSION:
        raise ReportError(f"Versión de informe no soportada: {version}")

    roots = [Path(root) for root in payload.get("roots", [])]
    duplicate_groups: list[DuplicateGroup] = []

    for group_data in payload.get("duplicate_groups", []):
        files = [
            FileRecord(path=Path(file_path), size=group_data["size"])
            for file_path in group_data.get("files", [])
        ]
        duplicate_groups.append(
            DuplicateGroup(
                digest=group_data["digest"],
                size=group_data["size"],
                files=files,
            )
        )

    return ScanResult(
        roots=roots,
        duplicate_groups=duplicate_groups,
        scanned_files=payload.get("scanned_files", 0),
        skipped_files=payload.get("skipped_files", 0),
        total_bytes_scanned=payload.get("total_bytes_scanned", 0),
    )
