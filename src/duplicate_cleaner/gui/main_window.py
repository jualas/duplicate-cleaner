from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from duplicate_cleaner.config import ScanOptions, normalize_roots
from duplicate_cleaner.gui.scan_worker import ScanWorker
from duplicate_cleaner.models import ScanResult
from duplicate_cleaner.reporting import format_bytes

PATH_ROLE = Qt.ItemDataRole.UserRole + 1


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Duplicate Cleaner")
        self.resize(1100, 720)

        self._scan_result: ScanResult | None = None
        self._worker: ScanWorker | None = None

        self._folder_list = QListWidget()
        self._min_size_spin = QSpinBox()
        self._algorithm_combo = QComboBox()
        self._follow_symlinks = QCheckBox("Seguir enlaces simbólicos")
        self._scan_button = QPushButton("Escanear")
        self._progress = QProgressBar()
        self._status_label = QLabel("Añade carpetas y pulsa Escanear.")
        self._summary_label = QLabel("Sin resultados.")
        self._tree = QTreeWidget()
        self._keep_combo = QComboBox()
        self._apply_keep_button = QPushButton("Marcar duplicados")
        self._delete_button = QPushButton("Eliminar seleccionados")
        self._selection_label = QLabel("Seleccionados: 0 archivos (0 B)")

        self._build_ui()
        self._wire_events()
        self._set_scanning(False)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        folders_box = QGroupBox("Carpetas a analizar")
        folders_layout = QVBoxLayout(folders_box)
        folders_layout.addWidget(self._folder_list)

        folder_buttons = QHBoxLayout()
        add_button = QPushButton("Añadir…")
        add_button.clicked.connect(self._add_folder)
        remove_button = QPushButton("Quitar")
        remove_button.clicked.connect(self._remove_folder)
        folder_buttons.addWidget(add_button)
        folder_buttons.addWidget(remove_button)
        folder_buttons.addStretch()
        folders_layout.addLayout(folder_buttons)

        options_box = QGroupBox("Opciones")
        options_layout = QHBoxLayout(options_box)
        self._min_size_spin.setRange(0, 1_048_576)
        self._min_size_spin.setValue(1)
        self._min_size_spin.setSuffix(" KB")
        self._algorithm_combo.addItems(["sha256", "md5", "sha1"])
        options_layout.addWidget(QLabel("Tamaño mínimo"))
        options_layout.addWidget(self._min_size_spin)
        options_layout.addWidget(QLabel("Hash"))
        options_layout.addWidget(self._algorithm_combo)
        options_layout.addWidget(self._follow_symlinks)
        options_layout.addStretch()

        scan_row = QHBoxLayout()
        scan_row.addWidget(self._scan_button)
        scan_row.addWidget(self._progress, stretch=1)
        layout.addWidget(folders_box)
        layout.addWidget(options_box)
        layout.addLayout(scan_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._summary_label)

        self._tree.setHeaderLabels(["Eliminar", "Ruta", "Tamaño", "Modificado"])
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        actions_row = QHBoxLayout()
        self._keep_combo.addItem("Conservar el más antiguo", "oldest")
        self._keep_combo.addItem("Conservar el más reciente", "newest")
        self._keep_combo.addItem("Conservar el primero (A-Z)", "first")
        actions_row.addWidget(QLabel("Estrategia"))
        actions_row.addWidget(self._keep_combo)
        actions_row.addWidget(self._apply_keep_button)
        actions_row.addStretch()
        actions_row.addWidget(self._selection_label)
        actions_row.addWidget(self._delete_button)

        splitter = QSplitter(Qt.Orientation.Vertical)
        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.addWidget(self._tree)
        tree_layout.addLayout(actions_row)
        splitter.addWidget(tree_container)
        splitter.setStretchFactor(0, 1)
        layout.addWidget(splitter, stretch=1)

        self.setCentralWidget(root)

    def _wire_events(self) -> None:
        self._scan_button.clicked.connect(self._start_scan)
        self._apply_keep_button.clicked.connect(self._apply_keep_strategy)
        self._delete_button.clicked.connect(self._delete_selected)
        self._tree.itemChanged.connect(self._update_selection_summary)

    def _add_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta")
        if not directory:
            return
        for index in range(self._folder_list.count()):
            if self._folder_list.item(index).text() == directory:
                return
        self._folder_list.addItem(directory)

    def _remove_folder(self) -> None:
        for item in self._folder_list.selectedItems():
            row = self._folder_list.row(item)
            self._folder_list.takeItem(row)

    def _build_options(self) -> ScanOptions:
        paths = [Path(self._folder_list.item(i).text()) for i in range(self._folder_list.count())]
        roots = normalize_roots(paths)
        min_size_kb = self._min_size_spin.value()
        min_size = 0 if min_size_kb == 0 else min_size_kb * 1024
        return ScanOptions(
            roots=roots,
            min_size=min_size,
            algorithm=self._algorithm_combo.currentText(),
            follow_symlinks=self._follow_symlinks.isChecked(),
        )

    def _start_scan(self) -> None:
        if self._folder_list.count() == 0:
            QMessageBox.warning(self, "Duplicate Cleaner", "Añade al menos una carpeta.")
            return
        try:
            options = self._build_options()
        except (FileNotFoundError, NotADirectoryError) as exc:
            QMessageBox.critical(self, "Duplicate Cleaner", str(exc))
            return

        self._tree.clear()
        self._scan_result = None
        self._set_scanning(True)
        self._progress.setRange(0, 0)
        self._status_label.setText("Descubriendo archivos…")

        self._worker = ScanWorker(options)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished_ok.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()

    def _on_scan_progress(self, phase: str, current: int, total: int) -> None:
        if phase == "discover":
            self._progress.setRange(0, 0)
            self._status_label.setText(f"Descubriendo archivos… {current}")
            return

        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(current)
            self._status_label.setText(f"Calculando hashes… {current}/{total}")
        else:
            self._progress.setRange(0, 0)
            self._status_label.setText("Calculando hashes…")

    def _on_scan_finished(self, result: ScanResult) -> None:
        self._scan_result = result
        self._populate_tree(result)
        self._summary_label.setText(
            f"Analizados: {result.scanned_files} archivos ({format_bytes(result.total_bytes_scanned)}) · "
            f"Grupos: {len(result.duplicate_groups)} · "
            f"Recuperable: {format_bytes(result.wasted_bytes)}"
        )
        self._status_label.setText("Escaneo completado.")
        self._progress.setRange(0, 1)
        self._progress.setValue(1)
        self._set_scanning(False)
        self._apply_keep_strategy()
        self._update_selection_summary()

    def _on_scan_failed(self, message: str) -> None:
        self._set_scanning(False)
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._status_label.setText("Error durante el escaneo.")
        QMessageBox.critical(self, "Duplicate Cleaner", message)

    def _populate_tree(self, result: ScanResult) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        for index, group in enumerate(result.duplicate_groups, start=1):
            group_item = QTreeWidgetItem(
                [
                    "",
                    f"Grupo {index} · {len(group.files)} archivos · "
                    f"{format_bytes(group.wasted_bytes)} recuperables",
                    format_bytes(group.size),
                    "",
                ]
            )
            group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self._tree.addTopLevelItem(group_item)

            for record in group.files:
                modified = self._format_mtime(record.path)
                child = QTreeWidgetItem(["", str(record.path), format_bytes(record.size), modified])
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Unchecked)
                child.setData(0, PATH_ROLE, str(record.path))
                group_item.addChild(child)
            group_item.setExpanded(True)
        self._tree.blockSignals(False)

    def _apply_keep_strategy(self) -> None:
        keep = self._keep_combo.currentData()
        self._tree.blockSignals(True)
        for group_index in range(self._tree.topLevelItemCount()):
            group_item = self._tree.topLevelItem(group_index)
            if group_item is None or group_item.childCount() == 0:
                continue
            keep_index = self._resolve_keep_index(group_item, keep)
            for child_index in range(group_item.childCount()):
                child = group_item.child(child_index)
                if child is None:
                    continue
                delete = child_index != keep_index
                child.setCheckState(
                    0,
                    Qt.CheckState.Checked if delete else Qt.CheckState.Unchecked,
                )
        self._tree.blockSignals(False)
        self._update_selection_summary()

    def _resolve_keep_index(self, group_item: QTreeWidgetItem, keep: str) -> int:
        entries: list[tuple[int, Path, float]] = []
        for child_index in range(group_item.childCount()):
            child = group_item.child(child_index)
            if child is None:
                continue
            path = Path(child.data(0, PATH_ROLE))
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            entries.append((child_index, path, mtime))

        if not entries:
            return 0
        if keep == "newest":
            return max(entries, key=lambda item: item[2])[0]
        if keep == "oldest":
            return min(entries, key=lambda item: item[2])[0]
        return min(entries, key=lambda item: str(item[1]))[0]

    def _collect_selected_paths(self) -> list[Path]:
        selected: list[Path] = []
        for group_index in range(self._tree.topLevelItemCount()):
            group_item = self._tree.topLevelItem(group_index)
            if group_item is None:
                continue
            for child_index in range(group_item.childCount()):
                child = group_item.child(child_index)
                if child is None or child.checkState(0) != Qt.CheckState.Checked:
                    continue
                selected.append(Path(child.data(0, PATH_ROLE)))
        return selected

    def _delete_selected(self) -> None:
        paths = self._collect_selected_paths()
        if not paths:
            QMessageBox.information(self, "Duplicate Cleaner", "No hay archivos marcados para eliminar.")
            return

        total_bytes = 0
        existing_paths: list[Path] = []
        for path in paths:
            if not path.exists():
                continue
            try:
                total_bytes += path.stat().st_size
            except OSError:
                continue
            existing_paths.append(path)

        if not existing_paths:
            QMessageBox.information(self, "Duplicate Cleaner", "Los archivos seleccionados ya no existen.")
            self._refresh_tree_after_delete(set(paths))
            return

        answer = QMessageBox.question(
            self,
            "Confirmar eliminación",
            f"¿Eliminar {len(existing_paths)} archivos ({format_bytes(total_bytes)})?\n"
            "Esta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        errors: list[str] = []
        for path in existing_paths:
            try:
                path.unlink()
                deleted += 1
            except OSError as exc:
                errors.append(f"{path}: {exc}")

        self._refresh_tree_after_delete(set(existing_paths))
        message = f"Eliminados: {deleted} archivos."
        if errors:
            message += f"\n\nErrores ({len(errors)}):\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                message += f"\n… y {len(errors) - 5} más."
        QMessageBox.information(self, "Duplicate Cleaner", message)

    def _refresh_tree_after_delete(self, deleted_paths: set[Path]) -> None:
        self._tree.blockSignals(True)
        for group_index in range(self._tree.topLevelItemCount() - 1, -1, -1):
            group_item = self._tree.topLevelItem(group_index)
            if group_item is None:
                continue
            for child_index in range(group_item.childCount() - 1, -1, -1):
                child = group_item.child(child_index)
                if child is None:
                    continue
                path = Path(child.data(0, PATH_ROLE))
                if path in deleted_paths:
                    group_item.removeChild(child)
            if group_item.childCount() <= 1:
                self._tree.takeTopLevelItem(group_index)
        self._tree.blockSignals(False)
        self._update_selection_summary()

    def _update_selection_summary(self) -> None:
        paths = self._collect_selected_paths()
        total_bytes = 0
        for path in paths:
            if not path.exists():
                continue
            try:
                total_bytes += path.stat().st_size
            except OSError:
                continue
        self._selection_label.setText(
            f"Seleccionados: {len(paths)} archivos ({format_bytes(total_bytes)})"
        )
        has_groups = self._tree.topLevelItemCount() > 0
        self._delete_button.setEnabled(has_groups and len(paths) > 0)

    def _set_scanning(self, active: bool) -> None:
        self._scan_button.setEnabled(not active)
        self._folder_list.setEnabled(not active)
        self._min_size_spin.setEnabled(not active)
        self._algorithm_combo.setEnabled(not active)
        self._follow_symlinks.setEnabled(not active)
        self._apply_keep_button.setEnabled(not active and self._tree.topLevelItemCount() > 0)
        self._delete_button.setEnabled(not active and len(self._collect_selected_paths()) > 0)

    @staticmethod
    def _format_mtime(path: Path) -> str:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            return "—"


def create_main_window() -> MainWindow:
    return MainWindow()
