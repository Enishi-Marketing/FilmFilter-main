"""Input-folder file browser widget for the FilmFilter editor."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp",
    ".heic", ".heif",
    ".arw", ".cr2", ".cr3", ".nef", ".nrw", ".raf", ".dng", ".rw2", ".orf", ".pef",
}


class FileBrowser(QWidget):
    """Filename list with multi-select for the input folder."""

    browse_requested = Signal()
    current_changed = Signal(object)  # Path or None
    selection_changed = Signal()

    def __init__(self, input_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._input_dir = input_dir

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        self._dir_label = QLabel("", self)
        self._dir_label.setStyleSheet("color: #888; font-size: 11px;")
        header.addWidget(self._dir_label, 1)
        browse = QPushButton("Browse...", self)
        browse.setToolTip("Choose input folder")
        browse.clicked.connect(self.browse_requested.emit)
        header.addWidget(browse)
        refresh = QPushButton("↻", self)
        refresh.setFixedWidth(28)
        refresh.setToolTip("Refresh file list")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        layout.addLayout(header)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setUniformItemSizes(True)
        self._list.setIconSize(QSize(0, 0))
        self._list.itemSelectionChanged.connect(self._emit_selection)
        self._list.currentItemChanged.connect(self._emit_current)
        layout.addWidget(self._list, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(4)
        self._select_all = QPushButton("Select all", self)
        self._select_all.clicked.connect(self._list.selectAll)
        self._select_none = QPushButton("Clear", self)
        self._select_none.clicked.connect(self._list.clearSelection)
        bottom.addWidget(self._select_all)
        bottom.addWidget(self._select_none)
        layout.addLayout(bottom)

        self._count_label = QLabel("", self)
        self._count_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._count_label)

        self.set_input_dir(input_dir)

    def set_input_dir(self, input_dir: Path) -> None:
        self._input_dir = input_dir
        self._dir_label.setText(str(input_dir))
        self.refresh()

    def refresh(self) -> None:
        previous = self.current_path()
        self._list.clear()
        if not self._input_dir.exists():
            self._count_label.setText("(folder missing)")
            self.current_changed.emit(None)
            return
        files = sorted(
            (p for p in self._input_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS),
            key=lambda p: p.name.lower(),
        )
        for path in files:
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self._list.addItem(item)
        self._count_label.setText(f"{len(files)} image(s)")
        restored = False
        if previous is not None:
            for row in range(self._list.count()):
                if self._list.item(row).data(Qt.ItemDataRole.UserRole) == str(previous):
                    self._list.setCurrentRow(row)
                    restored = True
                    break
        if not restored and self._list.count() > 0:
            self._list.setCurrentRow(0)
        elif self._list.count() == 0:
            self.current_changed.emit(None)
        self._emit_selection()

    def current_path(self) -> Path | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return Path(item.data(Qt.ItemDataRole.UserRole))

    def selected_paths(self) -> list[Path]:
        items = self._list.selectedItems()
        return [Path(item.data(Qt.ItemDataRole.UserRole)) for item in items]

    def all_paths(self) -> list[Path]:
        return [
            Path(self._list.item(row).data(Qt.ItemDataRole.UserRole))
            for row in range(self._list.count())
        ]

    def _emit_current(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            self.current_changed.emit(None)
            return
        self.current_changed.emit(Path(current.data(Qt.ItemDataRole.UserRole)))

    def _emit_selection(self) -> None:
        self.selection_changed.emit()
