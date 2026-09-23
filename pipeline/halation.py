"""Highlight halation and bloom inspired by imperfect consumer optics."""

from __future__ import annotations

import cv2
import numpy as np


def apply_halation(
    image: np.ndarray,
    *,
    strength: float = 0.055,
    intensity_percent: float = 100.0,
    threshold: float = 0.72,
    radius: float = 9.0,
    warmth: tuple[float, float, float] = (1.0, 0.42, 0.18),
) -> np.ndarray:
    """Add a faint warm glow around bright regions.

    Real film halation and inexpensive lenses both soften intense highlights in
    ways that feel emotional rather than clinically sharp. This stage isolates
    only the upper luminance range, blurs it, warms it, and adds it back softly so
    the image gains atmosphere without becoming a fantasy bloom effect.

    ``strength`` defines the base glow recipe. ``intensity_percent`` is the preset
    tuning control for backing the effect off without changing threshold, radius,
    or warmth; 100 preserves the base look, while lower values keep the same
    character with less visible bloom.
    """
    img = np.clip(image.astype(np.float32, copy=False), 0.0, 1.0)
    luminance = np.dot(img, np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))
    mask = np.clip((luminance - threshold) / max(1.0 - threshold, 1e-6), 0.0, 1.0)
    mask = mask * mask

    highlight = img * mask[..., None]
    sigma = max(float(radius), 0.1)
    blurred = cv2.GaussianBlur(highlight, ksize=(0, 0), sigmaX=sigma, sigmaY=sigma)
    tint = np.array(warmth, dtype=np.float32)
    intensity = np.clip(float(intensity_percent), 0.0, 200.0) / 100.0
    glow = blurred * tint[None, None, :] * strength * intensity

    return np.clip(img + glow, 0.0, 1.0)
