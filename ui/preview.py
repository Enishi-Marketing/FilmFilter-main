"""Background preview rendering for the FilmFilter editor.

The preview worker loads the source image once at viewer resolution and re-runs
the pipeline whenever parameters change. Rendering happens on a Qt worker
thread so slider drags never block the UI.
"""

from __future__ import annotations

import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from PySide6.QtCore import QMutex, QObject, QThread, QWaitCondition, Signal

from pipeline.pipeline import FilmPipeline, read_image


VIEWER_LONG_EDGE = 1280  # pixels


def downsample_for_preview(image: np.ndarray, long_edge: int = VIEWER_LONG_EDGE) -> np.ndarray:
    """Scale a float RGB image down so its longest side equals ``long_edge``."""
    h, w = image.shape[:2]
    if max(h, w) <= long_edge:
        return image
    scale = long_edge / float(max(h, w))
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    rgb = (np.clip(image, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    pil = Image.fromarray(rgb, mode="RGB").resize((new_w, new_h), Image.Resampling.LANCZOS)
    return np.asarray(pil, dtype=np.float32) / 255.0


class PreviewWorker(QObject):
    """Render preview images for the editor without blocking the UI thread.

    The worker keeps a single 'pending' preset and source path. New requests
    overwrite the pending state, so a flurry of slider events collapses into one
    render plus at most one follow-up. The worker loops on a wait condition so
    it sleeps cheaply between renders.
    """

    rendered = Signal(object, str)  # processed image (HxWx3 uint8 sRGB), source path
    original_ready = Signal(object, str)  # unprocessed downsample (HxWx3 uint8 sRGB), source path
    failed = Signal(str, str)        # error message, source path
    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._mutex = QMutex()
        self._wake = QWaitCondition()
        self._stop = False
        self._pending_path: str | None = None
        self._pending_preset: dict[str, Any] | None = None
        self._cached_path: str | None = None
        self._cached_image: np.ndarray | None = None

    def request(self, source_path: str | Path, preset: dict[str, Any]) -> None:
        """Schedule a new preview render. Replaces any earlier pending request."""
        path = str(source_path)
        self._mutex.lock()
        try:
            self._pending_path = path
            self._pending_preset = deepcopy(preset)
            self._wake.wakeAll()
        finally:
            self._mutex.unlock()

    def stop(self) -> None:
        """Tell the worker loop to exit at the next opportunity."""
        self._mutex.lock()
        try:
            self._stop = True
            self._wake.wakeAll()
        finally:
            self._mutex.unlock()

    def run(self) -> None:
        """Worker entry point — installed by the host thread via started.connect."""
        while True:
            self._mutex.lock()
            while not self._stop and self._pending_preset is None:
                self.busy_changed.emit(False)
                self._wake.wait(self._mutex)
            if self._stop:
                self._mutex.unlock()
                return
            path = self._pending_path
            preset = self._pending_preset
            self._pending_preset = None
            self._pending_path = None
            self._mutex.unlock()

            if path is None or preset is None:
                continue

            self.busy_changed.emit(True)
            try:
                rendered = self._render(path, preset)
            except Exception as exc:  # surface pipeline errors instead of dying silently
                self.failed.emit(f"{type(exc).__name__}: {exc}", path)
                continue
            self.rendered.emit(rendered, path)

    def _render(self, path: str, preset: dict[str, Any]) -> np.ndarray:
        if self._cached_path != path or self._cached_image is None:
            image = read_image(path)
            self._cached_image = downsample_for_preview(image)
            self._cached_path = path
            # Emit the unprocessed downsample once per cache load so the host
            # window can toggle a before/after compare without re-decoding the
            # source. The same array is reused across parameter changes.
            original8 = (np.clip(self._cached_image, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
            self.original_ready.emit(np.ascontiguousarray(original8), path)
        assert self._cached_image is not None
        pipeline = FilmPipeline(preset)
        out_float = pipeline.process(self._cached_image)
        out8 = (np.clip(out_float, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        return np.ascontiguousarray(out8)


def make_preview_thread(worker: PreviewWorker) -> QThread:
    """Wire a preview worker into a dedicated QThread."""
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    return thread


def shutdown_preview(worker: PreviewWorker, thread: QThread, timeout_ms: int = 4000) -> None:
    """Stop and join the preview worker thread cleanly."""
    worker.stop()
    thread.quit()
    if not thread.wait(timeout_ms):
        thread.terminate()
        thread.wait()
    # Tiny pause to let any in-flight cv2 ops cool off.
    time.sleep(0)
