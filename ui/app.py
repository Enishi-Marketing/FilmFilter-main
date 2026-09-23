"""FilmFilter desktop editor.

Top-level layout:

    +---------------------+--------------------------+----------------------+
    | File browser        | Preview canvas           | Parameter panel     |
    | (left, ~240 px)     | (centre, expandable)     | (right, ~360 px)    |
    +---------------------+--------------------------+----------------------+
    | Status bar with batch export progress + buttons                       |
    +-----------------------------------------------------------------------+

The parameter panel is built from ``ui.schema`` so every pipeline parameter
appears with the correct widget type, range, and default. Parameter changes
push a debounced render request to the preview worker; preset switches refresh
all controls from disk. Batch export runs on its own worker thread and writes
full-resolution JPEGs to the output folder.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from pipeline.pipeline import PRESET_DIR

from .controls import (
    BoolControl,
    ChoiceControl,
    Color3Control,
    FloatControl,
    IntControl,
    build_control,
)
from .export import ExportWorker
from .file_browser import FileBrowser
from .preview import PreviewWorker, make_preview_thread, shutdown_preview
from .presets import (
    list_preset_files,
    load_preset_normalized,
    merge_with_schema_defaults,
    save_preset,
    slugify,
    unique_preset_path,
)
from .schema import SCHEMA, STAGE_ORDER, default_preset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "input"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
PREVIEW_DEBOUNCE_MS = 90


class PreviewView(QLabel):
    """QLabel that scales its pixmap to fit while preserving aspect ratio."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setStyleSheet("background-color: #111;")
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        self._source: QPixmap | None = None
        self._placeholder = "Select an image to preview"
        self.setText(self._placeholder)
        self.setStyleSheet("background-color: #111; color: #777;")

    def set_image(self, rgb: np.ndarray | None) -> None:
        if rgb is None:
            self._source = None
            self.setText(self._placeholder)
            self.setPixmap(QPixmap())
            return
        h, w, _ = rgb.shape
        contiguous = np.ascontiguousarray(rgb)
        image = QImage(contiguous.data, w, h, w * 3, QImage.Format.Format_RGB888)
        # Detach from the numpy buffer so the pixmap is safe past this call.
        self._source = QPixmap.fromImage(image.copy())
        self._rescale()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._source is None:
            return
        scaled = self._source.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setText("")
        self.setPixmap(scaled)


class StagePanel(QGroupBox):
    """One collapsible stage section in the parameter panel."""

    changed = Signal()

    def __init__(self, stage_name: str, parent: QWidget | None = None) -> None:
        from .schema import STAGE_BY_NAME  # local import to keep header tidy

        stage = STAGE_BY_NAME[stage_name]
        super().__init__(stage.label, parent)
        self._stage_name = stage_name
        self.setCheckable(True)
        self.setChecked(stage.enabled_default)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)

        self._controls: dict[str, QWidget] = {}
        for param in stage.params:
            control = build_control(param, self)
            self._controls[param.name] = control
            layout.addWidget(control)
            control.valueChanged.connect(self._on_param_changed)

        self.toggled.connect(self._on_param_changed)

    def stage_name(self) -> str:
        return self._stage_name

    def enabled(self) -> bool:
        return self.isChecked()

    def set_enabled_value(self, value: bool) -> None:
        blocked = self.blockSignals(True)
        self.setChecked(bool(value))
        self.blockSignals(blocked)

    def set_values(self, block: dict[str, Any]) -> None:
        """Apply a preset effects block to this stage's controls."""
        self.set_enabled_value(bool(block.get("enabled", True)))
        for name, control in self._controls.items():
            if name in block:
                blocked = control.blockSignals(True)
                try:
                    control.set_value(block[name])
                finally:
                    control.blockSignals(blocked)

    def values(self) -> dict[str, Any]:
        """Return the current effects block for this stage."""
        out: dict[str, Any] = {"enabled": self.isChecked()}
        for name, control in self._controls.items():
            value: Any
            if isinstance(control, FloatControl):
                value = control.value()
            elif isinstance(control, IntControl):
                value = control.value()
            elif isinstance(control, BoolControl):
                value = control.value()
            elif isinstance(control, ChoiceControl):
                value = control.value()
            elif isinstance(control, Color3Control):
                value = list(control.value())
            else:
                continue
            out[name] = value
        return out

    def _on_param_changed(self, *_args) -> None:
        self.changed.emit()


class FilmFilterMainWindow(QMainWindow):
    """Top-level window for the FilmFilter editor."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FilmFilter")
        self.resize(1500, 900)

        self._input_dir = DEFAULT_INPUT_DIR
        self._output_dir = DEFAULT_OUTPUT_DIR
        self._current_image_path: Path | None = None
        self._suppress_param_changes = False
        self._dirty = False
        self._current_preset_path: Path | None = None
        self._loaded_preset_snapshot: dict[str, Any] = {}
        self._export_thread: QThread | None = None
        self._export_worker: ExportWorker | None = None
        self._export_total = 0
        self._export_done = 0
        # Latest processed + unprocessed preview frames for the compare toggle.
        self._latest_processed: np.ndarray | None = None
        self._latest_original: np.ndarray | None = None
        self._showing_original = False

        self._build_ui()
        self._wire_preview_thread()

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._render_timer.timeout.connect(self._render_now)

        self._refresh_preset_list()
        self._select_initial_preset()

        # FileBrowser already emitted its first current_changed during construction,
        # before this window connected to it. Pull the current selection so the
        # initial preview renders.
        self._current_image_path = self._file_browser.current_path()
        if self._current_image_path is not None:
            self._schedule_render(force_immediate=True)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save_preset_dialog)
        QShortcut(QKeySequence("Ctrl+Shift+E"), self, activated=self._export_all)
        # Backslash toggles compare, matching the Lightroom / Capture One default.
        QShortcut(QKeySequence("\\"), self, activated=self._toggle_compare)

    # ----- UI construction ------------------------------------------------

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)

        self._file_browser = FileBrowser(self._input_dir, self)
        self._file_browser.setMinimumWidth(220)
        self._file_browser.browse_requested.connect(self._browse_input_dir)
        self._file_browser.current_changed.connect(self._on_file_selected)
        self._file_browser.selection_changed.connect(self._update_export_buttons)
        splitter.addWidget(self._file_browser)

        # Centre column: preview + status above the export buttons.
        centre = QWidget(self)
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(6, 6, 6, 6)
        centre_layout.setSpacing(6)
        self._preview = PreviewView(centre)
        centre_layout.addWidget(self._preview, 1)

        # Bottom strip: compare toggle on the left, preview status on the right.
        strip = QHBoxLayout()
        strip.setContentsMargins(0, 0, 0, 0)
        strip.setSpacing(8)
        self._compare_btn = QPushButton("Show original", centre)
        self._compare_btn.setCheckable(True)
        self._compare_btn.setToolTip("Toggle the unfiltered original (shortcut: \\)")
        self._compare_btn.toggled.connect(self._set_compare)
        strip.addWidget(self._compare_btn)
        self._preview_status = QLabel("Idle", centre)
        self._preview_status.setStyleSheet("color: #888; font-size: 11px;")
        strip.addWidget(self._preview_status, 1)
        centre_layout.addLayout(strip)

        splitter.addWidget(centre)

        # Right column: preset row + scrollable parameter panel.
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(8)
        right_layout.addWidget(self._build_preset_row(right))

        scroll = QScrollArea(right)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        params_container = QWidget()
        params_layout = QVBoxLayout(params_container)
        params_layout.setContentsMargins(2, 2, 2, 2)
        params_layout.setSpacing(8)
        self._stage_panels: dict[str, StagePanel] = {}
        for stage in SCHEMA:
            panel = StagePanel(stage.name, params_container)
            panel.changed.connect(self._on_param_changed)
            self._stage_panels[stage.name] = panel
            params_layout.addWidget(panel)
        params_layout.addStretch(1)
        scroll.setWidget(params_container)
        right_layout.addWidget(scroll, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([240, 880, 360])

        self.setCentralWidget(splitter)

        # Status bar with batch progress and export buttons.
        status = QStatusBar(self)
        self.setStatusBar(status)
        self._status_label = QLabel("Ready", status)
        status.addWidget(self._status_label, 1)
        self._export_progress = QProgressBar(status)
        self._export_progress.setMaximumWidth(220)
        self._export_progress.setVisible(False)
        status.addPermanentWidget(self._export_progress)
        self._export_selected_btn = QPushButton("Export selected", status)
        self._export_selected_btn.clicked.connect(self._export_selected)
        status.addPermanentWidget(self._export_selected_btn)
        self._export_all_btn = QPushButton("Export all", status)
        self._export_all_btn.clicked.connect(self._export_all)
        status.addPermanentWidget(self._export_all_btn)
        self._cancel_export_btn = QPushButton("Cancel", status)
        self._cancel_export_btn.clicked.connect(self._cancel_export)
        self._cancel_export_btn.setVisible(False)
        status.addPermanentWidget(self._cancel_export_btn)
        self._update_export_buttons()

    def _build_preset_row(self, parent: QWidget) -> QWidget:
        wrapper = QWidget(parent)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)
        row1.addWidget(QLabel("Preset:", wrapper))
        self._preset_combo = QComboBox(wrapper)
        self._preset_combo.setMinimumWidth(180)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_combo_changed)
        row1.addWidget(self._preset_combo, 1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)
        self._save_btn = QPushButton("Save", wrapper)
        self._save_btn.setToolTip("Overwrite the current preset on disk")
        self._save_btn.clicked.connect(self._save_preset_in_place)
        row2.addWidget(self._save_btn)
        self._save_as_btn = QPushButton("Save as…", wrapper)
        self._save_as_btn.clicked.connect(self._save_preset_dialog)
        row2.addWidget(self._save_as_btn)
        self._reload_btn = QPushButton("Revert", wrapper)
        self._reload_btn.setToolTip("Reload the current preset from disk")
        self._reload_btn.clicked.connect(self._revert_preset)
        row2.addWidget(self._reload_btn)
        layout.addLayout(row2)

        self._dirty_label = QLabel("", wrapper)
        self._dirty_label.setStyleSheet("color: #c98; font-size: 11px;")
        layout.addWidget(self._dirty_label)

        return wrapper

    # ----- Preview thread plumbing ---------------------------------------

    def _wire_preview_thread(self) -> None:
        self._preview_worker = PreviewWorker()
        self._preview_thread = make_preview_thread(self._preview_worker)
        self._preview_worker.rendered.connect(self._on_preview_rendered)
        self._preview_worker.original_ready.connect(self._on_preview_original)
        self._preview_worker.failed.connect(self._on_preview_failed)
        self._preview_worker.busy_changed.connect(self._on_preview_busy)
        self._preview_thread.start()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if not self._confirm_discard_dirty("Unsaved preset changes — quit anyway?"):
            event.ignore()
            return
        if self._export_worker is not None:
            self._export_worker.cancel()
        if self._export_thread is not None:
            self._export_thread.quit()
            self._export_thread.wait(4000)
        shutdown_preview(self._preview_worker, self._preview_thread)
        super().closeEvent(event)

    # ----- Preset loading / saving ---------------------------------------

    def _refresh_preset_list(self) -> None:
        blocked = self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        self._preset_combo.addItem("(defaults)", userData=None)
        for path in list_preset_files():
            self._preset_combo.addItem(path.stem, userData=str(path))
        self._preset_combo.blockSignals(blocked)

    def _select_initial_preset(self) -> None:
        # Prefer kodak_prima_400 if present, otherwise the first preset.
        for i in range(self._preset_combo.count()):
            data = self._preset_combo.itemData(i)
            if data and Path(data).stem == "kodak_prima_400":
                self._preset_combo.setCurrentIndex(i)
                return
        if self._preset_combo.count() > 1:
            self._preset_combo.setCurrentIndex(1)
        else:
            self._preset_combo.setCurrentIndex(0)

    def _current_preset_dict(self) -> dict[str, Any]:
        """Read every stage panel and assemble a preset dict."""
        effects = {name: panel.values() for name, panel in self._stage_panels.items()}
        preset: dict[str, Any] = {
            "name": self._preset_combo.currentText(),
            "description": self._loaded_preset_snapshot.get("description", ""),
            "pipeline": list(STAGE_ORDER),
            "effects": effects,
        }
        # Forward-preserve any non-schema stages from the source preset.
        for stage_name, block in self._loaded_preset_snapshot.get("effects", {}).items():
            if stage_name not in effects:
                preset["effects"][stage_name] = block
        return preset

    def _apply_preset(self, preset: dict[str, Any]) -> None:
        merged = merge_with_schema_defaults(preset)
        self._suppress_param_changes = True
        try:
            for stage_name, panel in self._stage_panels.items():
                panel.set_values(merged["effects"].get(stage_name, {}))
        finally:
            self._suppress_param_changes = False
        self._loaded_preset_snapshot = merged
        self._mark_clean()
        self._schedule_render()

    def _on_preset_combo_changed(self, _index: int) -> None:
        data = self._preset_combo.currentData()
        if self._dirty:
            decision = QMessageBox.question(
                self,
                "Unsaved changes",
                "Save changes to the current preset before switching?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if decision == QMessageBox.StandardButton.Save:
                if not self._save_preset_in_place():
                    self._restore_preset_combo_selection()
                    return
            elif decision == QMessageBox.StandardButton.Cancel:
                self._restore_preset_combo_selection()
                return

        if data is None:
            self._current_preset_path = None
            self._apply_preset(default_preset())
        else:
            path = Path(data)
            try:
                preset = load_preset_normalized(path)
            except Exception as exc:
                QMessageBox.critical(self, "Preset error", f"Failed to load {path.name}: {exc}")
                return
            self._current_preset_path = path
            self._apply_preset(preset)

    def _restore_preset_combo_selection(self) -> None:
        """Roll the combo back to the previously-loaded preset without firing change logic."""
        target = str(self._current_preset_path) if self._current_preset_path else None
        for i in range(self._preset_combo.count()):
            if self._preset_combo.itemData(i) == target:
                blocked = self._preset_combo.blockSignals(True)
                self._preset_combo.setCurrentIndex(i)
                self._preset_combo.blockSignals(blocked)
                return

    def _save_preset_in_place(self) -> bool:
        if self._current_preset_path is None:
            return self._save_preset_dialog()
        preset = self._current_preset_dict()
        try:
            save_preset(self._current_preset_path, preset)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self._loaded_preset_snapshot = preset
        self._mark_clean()
        self._status_label.setText(f"Saved {self._current_preset_path.name}")
        return True

    def _save_preset_dialog(self) -> bool:
        suggested = self._preset_combo.currentText() or "new_preset"
        if suggested == "(defaults)":
            suggested = "new_preset"
        name, ok = QInputDialog.getText(self, "Save preset as", "Preset name:", text=suggested)
        if not ok or not name.strip():
            return False
        stem = slugify(name)
        path = unique_preset_path(stem)
        preset = self._current_preset_dict()
        preset["name"] = name.strip()
        try:
            save_preset(path, preset)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self._refresh_preset_list()
        for i in range(self._preset_combo.count()):
            if self._preset_combo.itemData(i) == str(path):
                blocked = self._preset_combo.blockSignals(True)
                self._preset_combo.setCurrentIndex(i)
                self._preset_combo.blockSignals(blocked)
                break
        self._current_preset_path = path
        self._loaded_preset_snapshot = preset
        self._mark_clean()
        self._status_label.setText(f"Saved {path.name}")
        return True

    def _revert_preset(self) -> None:
        if self._current_preset_path is None:
            self._apply_preset(default_preset())
            return
        try:
            preset = load_preset_normalized(self._current_preset_path)
        except Exception as exc:
            QMessageBox.critical(self, "Reload failed", str(exc))
            return
        self._apply_preset(preset)
        self._status_label.setText(f"Reverted to {self._current_preset_path.name}")

    # ----- Dirty tracking -------------------------------------------------

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self._dirty_label.setText("● unsaved changes")

    def _mark_clean(self) -> None:
        self._dirty = False
        self._dirty_label.setText("")

    def _confirm_discard_dirty(self, prompt: str) -> bool:
        if not self._dirty:
            return True
        decision = QMessageBox.question(
            self,
            "Unsaved changes",
            prompt,
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if decision == QMessageBox.StandardButton.Save:
            return self._save_preset_in_place()
        return decision == QMessageBox.StandardButton.Discard

    # ----- Slider / preset interaction -----------------------------------

    def _on_param_changed(self) -> None:
        if self._suppress_param_changes:
            return
        self._mark_dirty()
        self._schedule_render()

    def _on_file_selected(self, path: Path | None) -> None:
        self._current_image_path = path
        # Drop cached frames so the compare toggle can't show stale data from
        # the previous image while the new render is in flight.
        self._latest_processed = None
        self._latest_original = None
        if path is None:
            self._preview.set_image(None)
            self._preview_status.setText("No image selected")
            return
        self._preview_status.setText(f"Loading {path.name}…")
        self._schedule_render(force_immediate=True)

    def _browse_input_dir(self) -> None:
        dialog = QFileDialog(self, "Choose input folder", str(self._input_dir))
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return
        selected = dialog.selectedFiles()
        if not selected:
            return
        self._input_dir = Path(selected[0])
        self._file_browser.set_input_dir(self._input_dir)
        self._status_label.setText(f"Input folder: {self._input_dir}")
        self._update_export_buttons()

    def _schedule_render(self, force_immediate: bool = False) -> None:
        if self._current_image_path is None:
            return
        if force_immediate:
            self._render_timer.stop()
            self._render_now()
        else:
            self._render_timer.start()

    def _render_now(self) -> None:
        if self._current_image_path is None:
            return
        preset = self._current_preset_dict()
        self._preview_worker.request(self._current_image_path, preset)

    def _on_preview_rendered(self, rgb: np.ndarray, source_path: str) -> None:
        if self._current_image_path is None or str(self._current_image_path) != source_path:
            return
        self._latest_processed = rgb
        if not self._showing_original:
            self._preview.set_image(rgb)
        self._preview_status.setText(f"{Path(source_path).name}  •  {rgb.shape[1]}×{rgb.shape[0]} preview")

    def _on_preview_original(self, rgb: np.ndarray, source_path: str) -> None:
        """Cache the unprocessed downsample for the compare toggle."""
        if self._current_image_path is None or str(self._current_image_path) != source_path:
            return
        self._latest_original = rgb
        if self._showing_original:
            self._preview.set_image(rgb)

    def _on_preview_failed(self, message: str, source_path: str) -> None:
        if self._current_image_path is not None and str(self._current_image_path) == source_path:
            self._preview_status.setText(f"Preview failed: {message}")

    def _on_preview_busy(self, busy: bool) -> None:
        if busy and not self._showing_original:
            self._preview_status.setText("Rendering…")

    # ----- Compare toggle -------------------------------------------------

    def _set_compare(self, show_original: bool) -> None:
        """Swap between the rendered preview and the unprocessed original."""
        self._showing_original = bool(show_original)
        # Keep the button's checked state in sync if this came in from a shortcut.
        if self._compare_btn.isChecked() != self._showing_original:
            blocked = self._compare_btn.blockSignals(True)
            self._compare_btn.setChecked(self._showing_original)
            self._compare_btn.blockSignals(blocked)
        if self._showing_original:
            self._compare_btn.setText("Showing original")
            if self._latest_original is not None:
                self._preview.set_image(self._latest_original)
            if self._current_image_path is not None:
                self._preview_status.setText(f"{self._current_image_path.name}  •  original (unfiltered)")
        else:
            self._compare_btn.setText("Show original")
            if self._latest_processed is not None:
                self._preview.set_image(self._latest_processed)
                self._preview_status.setText(
                    f"{Path(self._current_image_path).name}  •  "
                    f"{self._latest_processed.shape[1]}×{self._latest_processed.shape[0]} preview"
                    if self._current_image_path is not None
                    else ""
                )

    def _toggle_compare(self) -> None:
        self._set_compare(not self._showing_original)

    # ----- Export ---------------------------------------------------------

    def _update_export_buttons(self) -> None:
        running = self._export_worker is not None
        self._export_selected_btn.setEnabled(not running and bool(self._file_browser.selected_paths()))
        self._export_all_btn.setEnabled(not running and bool(self._file_browser.all_paths()))

    def _export_selected(self) -> None:
        files = self._file_browser.selected_paths()
        if not files:
            files = [self._current_image_path] if self._current_image_path else []
        self._start_export(files)

    def _export_all(self) -> None:
        self._start_export(self._file_browser.all_paths())

    def _start_export(self, files: list[Path]) -> None:
        files = [f for f in files if f is not None]
        if not files:
            QMessageBox.information(self, "Nothing to export", "Select at least one image in the file list.")
            return
        if self._export_worker is not None:
            return
        preset = self._current_preset_dict()
        preset_label = (
            self._current_preset_path.stem
            if self._current_preset_path is not None
            else slugify(self._preset_combo.currentText() or "preset")
        )
        worker = ExportWorker(
            files,
            self._output_dir,
            preset,
            preset_label,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_export_progress)
        worker.file_failed.connect(self._on_export_failure)
        worker.canceled.connect(lambda: self._status_label.setText("Export canceled"))
        worker.finished.connect(self._on_export_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._export_worker = worker
        self._export_thread = thread
        self._export_total = len(files)
        self._export_done = 0

        self._export_progress.setRange(0, len(files))
        self._export_progress.setValue(0)
        self._export_progress.setVisible(True)
        self._cancel_export_btn.setVisible(True)
        self._update_export_buttons()
        self._status_label.setText(f"Exporting 0/{len(files)}…")
        thread.start()

    def _cancel_export(self) -> None:
        if self._export_worker is not None:
            self._export_worker.cancel()
            self._status_label.setText("Canceling…")

    def _on_export_progress(self, done: int, total: int, current: str) -> None:
        self._export_done = done
        self._export_progress.setValue(done)
        self._export_progress.setMaximum(total)
        self._status_label.setText(f"Exporting {done}/{total} — {current}")

    def _on_export_failure(self, source: str, message: str) -> None:
        self._status_label.setText(f"Failed {Path(source).name}: {message}")

    def _on_export_finished(self, succeeded: int, failed: int) -> None:
        self._export_worker = None
        self._export_thread = None
        self._export_progress.setVisible(False)
        self._cancel_export_btn.setVisible(False)
        self._update_export_buttons()
        if failed == 0:
            self._status_label.setText(f"Exported {succeeded} image(s) to {self._output_dir}")
        else:
            self._status_label.setText(
                f"Exported {succeeded} image(s); {failed} failed. See terminal for details."
            )


def launch() -> int:
    """Launch the editor and run the Qt event loop."""
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    window = FilmFilterMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(launch())
