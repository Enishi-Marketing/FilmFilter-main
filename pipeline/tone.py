"""Tone shaping utilities for a soft consumer-film rendering."""

from __future__ import annotations

import numpy as np

from .tonal import LUMINANCE_WEIGHTS, luminance, smoothstep


def apply_tone(
    image: np.ndarray,
    *,
    black_lift: float = 0.045,
    contrast_softness: float = 0.18,
    highlight_compression: float = 0.38,
    shoulder_strength: float = 0.42,
    shadow_chroma_damping: float = 0.22,
    rolloff_start: float = 0.62,
    midtone_preservation: float = 0.65,
    lifted_black: float | None = None,
    contrast: float | None = None,
    highlight_rolloff: float | None = None,
) -> np.ndarray:
    """Shape scene contrast into a gentler print-like response.

    Consumer print scans often feel forgiving because deep shadows are not fully
    black and bright areas compress before clipping. Highlight behavior is one of
    the strongest cues that separates scanned film from digital capture: a creamy
    shoulder lets whites feel bright without turning harsh, synthetic, or gray.

    ``black_lift`` raises the shadow floor like paper density in a print scan.
    ``contrast_softness`` gently reduces brittle digital contrast while preserving
    ordinary midtone separation. ``highlight_compression`` controls how early the
    upper luminance range bends away from clipping, and ``shoulder_strength``
    controls how much of that rounded shoulder is blended into the image.
    ``shadow_chroma_damping`` reins in color casts that become more visible after
    the shadow floor is lifted, keeping blacks soft rather than stained.
    """
    img = np.clip(image.astype(np.float32, copy=False), 0.0, 1.0)

    # Accept the original parameter names so older presets keep working while the
    # public preset language moves toward clearer aesthetic controls.
    if lifted_black is not None:
        black_lift = lifted_black
    if contrast is not None:
        contrast_softness = np.clip((1.0 - contrast) / 0.45, 0.0, 1.0)
    if highlight_rolloff is not None:
        highlight_compression = highlight_rolloff

    luminance_values = luminance(img)

    # Reduce harsh global contrast around photographic middle gray without making
    # the whole frame feel flat. This trims digital precision before the shoulder.
    contrast_scale = 1.0 - np.clip(contrast_softness, 0.0, 1.0) * 0.45
    toned_luma = 0.5 + (luminance_values - 0.5) * contrast_scale

    # Lift blacks by raising the toe of the curve while leaving midtones usable.
    toe_mask = 1.0 - smoothstep(0.18, 0.72, toned_luma)
    toned_luma = toned_luma + black_lift * (1.0 - toned_luma) ** 2 * toe_mask

    # Compress highlights with a smooth luminance shoulder. Applying the curve to
    # luminance and scaling RGB preserves hue relationships better than bending
    # each channel independently, which can make whites look muddy or unstable.
    shoulder = smoothstep(rolloff_start, 1.0, toned_luma)
    high = np.maximum(toned_luma - rolloff_start, 0.0)
    compression = max(1.0 - float(highlight_compression) * 0.72, 0.12)
    compressed_highs = rolloff_start + (1.0 - rolloff_start) * (
        1.0 - np.exp(-high / max((1.0 - rolloff_start) * compression, 1e-6))
    )
    shoulder_mix = shoulder * np.clip(shoulder_strength, 0.0, 1.0)
    rolled_luma = toned_luma * (1.0 - shoulder_mix) + compressed_highs * shoulder_mix

    ratio = rolled_luma / np.maximum(luminance_values, 1e-5)
    rolled = img * ratio[..., None]

    # Near white, gently blend toward neutral paper-white to avoid colored clipping
    # while preserving enough channel relationship that highlights do not turn gray.
    neutral = rolled_luma[..., None]
    white_mask = smoothstep(0.82, 1.0, rolled_luma)[..., None] * 0.18 * shoulder_mix[..., None]
    rolled = rolled * (1.0 - white_mask) + neutral * white_mask

    # Apply the lifted toe directly to very dark pixels where luminance scaling has
    # little leverage because the original channel values are close to zero.
    shadow_fill = black_lift * (1.0 - smoothstep(0.0, 0.28, luminance_values))[..., None] * 0.32
    rolled = rolled + shadow_fill

    # Lifted blacks can reveal and exaggerate digital color casts. Pull only the
    # deepest shadows a little closer to neutral luminance so dark regions feel
    # like scanned print density rather than red or magenta contamination.
    shadow_neutral = np.dot(rolled, LUMINANCE_WEIGHTS)[..., None]
    shadow_color_mask = (
        (1.0 - smoothstep(0.06, 0.38, luminance_values))[..., None]
        * np.clip(shadow_chroma_damping, 0.0, 1.0)
    )
    rolled = rolled * (1.0 - shadow_color_mask) + shadow_neutral * shadow_color_mask

    # Blend back some original midtone structure so faces and ordinary objects keep
    # shape while shadows and highlights receive the print-like curve.
    mid_mask = 1.0 - np.abs(luminance_values - 0.5) * 2.0
    mid_mask = (
        np.clip(mid_mask[..., None], 0.0, 1.0)
        * np.clip(midtone_preservation, 0.0, 1.0)
        * (1.0 - shoulder[..., None] * 0.65)
    )
    result = rolled * (1.0 - mid_mask) + img * mid_mask

    return np.clip(result, 0.0, 1.0)
