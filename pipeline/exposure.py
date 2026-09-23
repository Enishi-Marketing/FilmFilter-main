"""Global exposure adjustment for pre-film tonal placement."""

from __future__ import annotations

import numpy as np


def apply_exposure(
    image: np.ndarray,
    *,
    exposure: float = 0.0,
) -> np.ndarray:
    """Shift the image up or down in photographic exposure stops.

    This stage behaves like a raw-editor exposure slider: positive values place
    the scene higher before the film shoulder, while negative values give the
    later tone stages more shadow density to shape. Keeping the adjustment in
    stops makes it predictable for users: +1 EV doubles brightness and -1 EV
    halves it, with the film pipeline handling highlight softness afterward.
    """
    img = np.clip(image.astype(np.float32, copy=False), 0.0, 1.0)
    scale = np.float32(2.0 ** float(exposure))
    return np.clip(img * scale, 0.0, 1.0)
