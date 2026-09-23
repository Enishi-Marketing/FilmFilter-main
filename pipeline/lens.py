"""Gentle lens imperfections for consumer-camera softness."""

from __future__ import annotations

import cv2
import numpy as np


def _radial_distance(height: int, width: int) -> np.ndarray:
    y, x = np.ogrid[-1.0:1.0:complex(height), -1.0:1.0:complex(width)]
    return np.sqrt(x * x + y * y).astype(np.float32)


def _radial_aberration(image: np.ndarray, aberration: float) -> np.ndarray:
    """Apply radially correct chromatic aberration.

    Real lateral CA is a magnification difference between wavelengths — the red
    focal plane is imaged at a slightly different scale than blue, so the shift
    is zero at the optical centre and increases proportionally with distance from
    it. A global pixel shift (the naive approach) creates fringing everywhere and
    produces visible artefacts in dark scenes. This implementation remaps each
    channel through a slightly different magnification so the displacement is
    physically zero at the centre and reaches its maximum only at the frame corners.
    """
    h, w = image.shape[:2]
    cx, cy = (w - 1) * 0.5, (h - 1) * 0.5

    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    px_x, px_y = np.meshgrid(xs, ys)

    # Normalized offset from centre, scaled so corner = 1 on the long axis.
    long_axis = float(max(cx, cy))
    nx = (px_x - cx) / long_axis
    ny = (px_y - cy) / long_axis
    r2 = (nx * nx + ny * ny).astype(np.float32)

    # scale controls the fractional magnification difference per unit r².
    # aberration=1 → ~4px displacement at a typical image corner.
    scale = float(aberration) * 0.004

    result = image.copy()
    for ch_idx, sign in ((0, 1.0), (2, -1.0)):  # red outward, blue inward
        divisor = 1.0 + sign * scale * r2
        src_x = (cx + (px_x - cx) / divisor).astype(np.float32)
        src_y = (cy + (px_y - cy) / divisor).astype(np.float32)
        result[..., ch_idx] = cv2.remap(
            image[..., ch_idx], src_x, src_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
    return result


def apply_lens(
    image: np.ndarray,
    *,
    vignette: float = 0.10,
    edge_softness: float = 0.18,
    aberration: float = 0.25,
) -> np.ndarray:
    """Introduce small optical imperfections without announcing themselves.

    Disposable and toy cameras rarely render corners as crisply or as evenly as
    the center. A restrained vignette, barely softer edges, and optional subpixel
    color separation create a consumer-grade photographic feeling while avoiding
    the heavy blur and extreme dark corners associated with novelty filters.
    """
    img = np.clip(image.astype(np.float32, copy=False), 0.0, 1.0)
    h, w = img.shape[:2]
    radius = _radial_distance(h, w)
    edge_mask = np.clip((radius - 0.35) / 0.85, 0.0, 1.0)[..., None]

    if edge_softness > 0.0:
        blurred = cv2.GaussianBlur(img, ksize=(0, 0), sigmaX=0.8 + edge_softness * 2.0)
        img = img * (1.0 - edge_mask * edge_softness) + blurred * (edge_mask * edge_softness)

    if aberration > 0.0:
        img = _radial_aberration(img, aberration)

    if vignette > 0.0:
        falloff = 1.0 - np.clip(radius / 1.35, 0.0, 1.0) ** 2 * vignette
        img = img * falloff[..., None]

    return np.clip(img, 0.0, 1.0)
