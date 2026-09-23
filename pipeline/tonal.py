"""Reusable tonal masks for smooth film-like regional behavior."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


LUMINANCE_WEIGHTS = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def luminance(image: np.ndarray) -> np.ndarray:
    """Return Rec. 709 luminance for RGB float data in the 0..1 range."""
    return np.dot(image, LUMINANCE_WEIGHTS)


def smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    """Return a smooth 0..1 transition with no hard edge at the endpoints."""
    t = np.clip((x - edge0) / max(edge1 - edge0, 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def tonal_masks(
    image_or_luminance: np.ndarray,
    *,
    shadow_end: float = 0.36,
    mid_center: float = 0.50,
    mid_width: float = 0.58,
    highlight_start: float = 0.58,
) -> dict[str, np.ndarray]:
    """Create naturally overlapping shadow, midtone, and highlight masks.

    Film-like operations rarely switch on at exact luminance boundaries. These
    masks overlap on purpose so color, grain, and shoulder behavior can pass
    between regions softly, preserving skin gradients and print-scan smoothness.
    The returned masks are single-channel arrays shaped ``H x W x 1``.
    """
    if image_or_luminance.ndim == 3 and image_or_luminance.shape[-1] == 3:
        lum = luminance(np.clip(image_or_luminance.astype(np.float32, copy=False), 0.0, 1.0))
    else:
        lum = np.clip(image_or_luminance.astype(np.float32, copy=False), 0.0, 1.0)

    shadow = 1.0 - smoothstep(0.04, shadow_end, lum)
    highlight = smoothstep(highlight_start, 0.96, lum)
    mid_distance = np.abs(lum - mid_center) / max(mid_width * 0.5, 1e-6)
    midtone = 1.0 - smoothstep(0.45, 1.0, mid_distance)

    return {
        "shadows": np.clip(shadow, 0.0, 1.0)[..., None],
        "midtones": np.clip(midtone, 0.0, 1.0)[..., None],
        "highlights": np.clip(highlight, 0.0, 1.0)[..., None],
    }


def blend_with_mask(
    image: np.ndarray,
    transformed: np.ndarray,
    mask: np.ndarray,
    *,
    strength: float = 1.0,
) -> np.ndarray:
    """Blend two RGB images through a smooth tonal mask and strength control."""
    amount = np.clip(mask, 0.0, 1.0) * np.clip(strength, 0.0, 1.0)
    return image * (1.0 - amount) + transformed * amount


def apply_masked_transform(
    image: np.ndarray,
    transform: Callable[[np.ndarray], np.ndarray],
    mask: np.ndarray,
    *,
    strength: float = 1.0,
) -> np.ndarray:
    """Apply a transform and blend it back through a tonal mask.

    This helper keeps regional color operations soft. It is useful for debugging
    and for effect modules that need a transform to exist mostly in shadows,
    midtones, or highlights without creating visible boundaries.
    """
    transformed = transform(image)
    return blend_with_mask(image, transformed, mask, strength=strength)


def visualize_masks(masks: dict[str, np.ndarray]) -> np.ndarray:
    """Pack shadow, midtone, and highlight masks into an RGB debug image.

    The preview maps shadows to blue, midtones to green, and highlights to red.
    It is intended for local inspection and should not be used as a committed
    output artifact.
    """
    return np.concatenate(
        (masks["highlights"], masks["midtones"], masks["shadows"]),
        axis=-1,
    ).astype(np.float32)
