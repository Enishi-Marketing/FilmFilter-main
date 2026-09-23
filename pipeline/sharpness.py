"""Optional digital sharpness reduction for a scanned-print feel."""

from __future__ import annotations

import cv2
import numpy as np


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    """Return a smooth 0..1 transition for protecting stronger edges."""
    t = np.clip((x - edge0) / max(edge1 - edge0, 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def apply_sharpness(
    image: np.ndarray,
    *,
    soften_digital_sharpness: bool = False,
    sharpness_softening_strength: float = 0.18,
    microcontrast_reduction: float = 0.16,
) -> np.ndarray:
    """Reduce brittle digital microcontrast without making the image blurry.

    Modern files often carry edge contrast that feels too exact for consumer film
    scans. When enabled, this stage slightly attenuates fine high-frequency detail
    and applies a very mild edge-aware smoothing pass. Strong edges and facial
    structure are protected so the result reads as less digital, not defocused.
    """
    img = np.clip(image.astype(np.float32, copy=False), 0.0, 1.0)
    if not soften_digital_sharpness:
        return img

    strength = np.clip(sharpness_softening_strength, 0.0, 1.0)
    micro = np.clip(microcontrast_reduction, 0.0, 1.0)
    if strength <= 0.0 and micro <= 0.0:
        return img

    luminance = np.dot(img, np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))
    local_luma = cv2.GaussianBlur(luminance, ksize=(0, 0), sigmaX=0.75, sigmaY=0.75)
    local_detail = np.abs(luminance - local_luma)

    # Keep major edges intact and mainly soften small, brittle contrast changes.
    edge_protection = _smoothstep(0.025, 0.11, local_detail)[..., None]
    reduction = micro * (1.0 - edge_protection) * 0.42

    base = cv2.GaussianBlur(img, ksize=(0, 0), sigmaX=0.65, sigmaY=0.65)
    detail = img - base
    clarity_reduced = base + detail * (1.0 - reduction)

    bilateral = cv2.bilateralFilter(
        img,
        d=0,
        sigmaColor=0.018 + strength * 0.055,
        sigmaSpace=0.85 + strength * 1.45,
    )
    softened = img * (1.0 - strength * 0.30) + bilateral * (strength * 0.30)

    result = clarity_reduced * (micro * 0.65) + softened * (1.0 - micro * 0.65)
    return np.clip(result, 0.0, 1.0)
