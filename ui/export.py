"""Background batch export worker for the FilmFilter editor."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from pipeline.pipeline import FilmPipeline, read_image, write_image


class ExportWorker(QObject):
    """Process a list of source images at full resolution with the current preset.

    The worker is move-to-thread and run via ``QThread.started`` so cancelling
    only stops new images — the current image finishes its pipeline pass.
    """

    progress = Signal(int, int, str)   # done, total, current name
    file_done = Signal(str, str)        # source path, output path
    file_failed = Signal(str, str)      # source path, error message
    finished = Signal(int, int)         # success count, failure count
    canceled = Signal()

    def __init__(
        self,
        sources: list[Path],
        output_dir: Path,
        preset: dict[str, Any],
        preset_label: str,
        jpeg_quality: int = 95,
    ) -> None:
        super().__init__()
        self._sources = list(sources)
        self._output_dir = Path(output_dir)
        self._preset = deepcopy(preset)
        self._preset_label = preset_label
        self._jpeg_quality = int(jpeg_quality)
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        total = len(self._sources)
        if total == 0:
            self.finished.emit(0, 0)
            return
        self._output_dir.mkdir(parents=True, exist_ok=True)
        pipeline = FilmPipeline(self._preset)
        succeeded = 0
        failed = 0
        for i, src in enumerate(self._sources, 1):
            if self._cancel:
                self.canceled.emit()
                break
            self.progress.emit(i - 1, total, src.name)
            dest = self._output_dir / f"{src.stem}_{self._preset_label}.jpg"
            try:
                image = read_image(src)
                processed = pipeline.process(image)
                write_image(dest, processed, quality=self._jpeg_quality)
            except Exception as exc:
                failed += 1
                self.file_failed.emit(str(src), f"{type(exc).__name__}: {exc}")
                continue
            succeeded += 1
            self.file_done.emit(str(src), str(dest))
            self.progress.emit(i, total, src.name)
        self.finished.emit(succeeded, failed)
