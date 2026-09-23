"""Exposure-adaptive per-channel film emulsion curves.

Real color negative film has three independent dye layers — cyan, magenta, and
yellow — each with its own H&D (Hurter–Driffield) characteristic curve. The
curves differ in toe depth, shoulder onset, and midtone gamma. More importantly,
they react differently to the scene's spectral content: a channel that was more
heavily exposed develops a shallower toe and earlier shoulder, while an
underexposed channel has a deeper toe and more linear midrange.

This module measures each channel's actual exposure distribution from the image
and shifts the curve parameters accordingly, so the color rendering changes with
the scene rather than applying a fixed transform. The result is that warm
afternoon light behaves differently from flat overcast, and a backlit subject
creates different channel interactions than a front-lit one — without any manual
per-image settings.
"""

from __future__ import annotations

import numpy as np

from .tonal import smoothstep


# Film dye layer characteristics. Values derived from published H&D curves for
# ISO 400 color negative stocks. Green is the reference channel (gamma 1.0).
# Red (cyan dye): slightly warm rendering, earlier highlight compression.
# Blue (yellow dye): deepest toe, densest base, shoulder onset between R and G.
#
# base_lift models the orange base density of color negative film. The orange mask
# raises red and green floors well above blue, creating the characteristic warm
# shadow floor of print scans. Red lifts most, blue lifts least.
_CHANNEL = {
    "red":   {"toe_depth": 0.038, "shoulder_start": 0.70, "gamma": 0.96, "base_lift": 0.016},
    "green": {"toe_depth": 0.021, "shoulder_start": 0.77, "gamma": 1.00, "base_lift": 0.010},
    "blue":  {"toe_depth": 0.046, "shoulder_start": 0.73, "gamma": 1.05, "base_lift": 0.005},
}


def _exposure_stats(ch: np.ndarray) -> tuple[float, float, float]:
    """Return the 10th, 50th, and 95th percentile of a channel."""
    flat = ch.ravel()
    return (
        float(np.percentile(flat, 10)),
        float(np.percentile(flat, 50)),
        float(np.percentile(flat, 95)),
    )


def _channel_curve(
    x: np.ndarray,
    *,
    toe_depth: float,
    shoulder_start: float,
    gamma: float,
    base_lift: float,
    shoulder_compression: float,
) -> np.ndarray:
    """Apply a smooth parametric emulsion curve to a single channel.

    The curve has three continuously blended regions:
    - Toe: a luminance-dependent gamma that increases in the shadows, compressing
      dark values as each dye layer's density rises non-linearly at low exposure.
    - Midtone: the nominal per-channel gamma, approximating the linear portion of
      the H&D curve where density is proportional to log exposure.
    - Shoulder: an exponential rolloff preventing hard clipping, whose onset shifts
      with the channel's measured highlight saturation.
    """
    # Shadow-weighted gamma: blends from (gamma + toe_depth * 5) at black to
    # (gamma) in upper midtones. This creates the characteristic toe compression
    # without any hard boundary — a smooth power-law gradient across the range.
    toe_weight = (1.0 - smoothstep(0.0, shoulder_start * 0.58, x)) ** 1.8
    local_gamma = gamma + toe_depth * 5.0 * toe_weight
    curved = x ** np.clip(local_gamma, 0.4, 3.0)

    # Exponential shoulder: above shoulder_start the curve rolls off smoothly.
    # Using the curved (gamma-adjusted) value so the shoulder interacts with the
    # actual channel's perceptual range, not the raw linear input.
    above = np.maximum(curved - shoulder_start, 0.0)
    max_above = 1.0 - shoulder_start + 1e-6
    compressed = max_above * (1.0 - np.exp(-above / (max_above * max(shoulder_compression, 0.04))))
    curved = np.where(curved > shoulder_start, shoulder_start + compressed, curved)

    # Base lift: minimum density from film fog and paper white base.
    # Applied only in the shadow region — the orange base of colour negative film
    # raises the shadow floor, not highlights. Fades to zero by lower midtones so
    # sky and bright subjects are unaffected by the per-channel differential lift.
    shadow_lift_weight = 1.0 - smoothstep(0.0, 0.36, x)
    return np.clip(curved + base_lift * shadow_lift_weight, 0.0, 1.0)


def apply_curves(
    image: np.ndarray,
    *,
    exposure_adaptation: float = 0.70,
    shoulder_compression: float = 0.42,
) -> np.ndarray:
    """Apply independent exposure-adaptive per-channel emulsion curves.

    Each channel's toe and shoulder are measured and adjusted from the image's
    own statistics: a channel whose highlights are already saturated develops an
    earlier shoulder; one with heavy shadow density gets a deeper toe. Because the
    three channels rarely have identical exposure distributions, the color balance
    shifts naturally with scene content — warm light causes red to clip first and
    pull the overall rendering warm, flat or cool light leaves green as the last
    channel standing, matching the spectral behaviour of the emulsion.

    ``exposure_adaptation`` controls how strongly the measured exposure moves the
    curve inflection points. At 0.0 the curves are fixed to the channel defaults;
    at 1.0 the scene exposure fully determines where the toe and shoulder land.

    ``shoulder_compression`` sets how gradually the shoulder rolls off. Lower
    values produce a more abrupt shoulder (faster clip); higher values give a long
    creamy rolloff like a fine-grain portrait stock.
    """
    img = np.clip(image.astype(np.float32, copy=False), 0.0, 1.0)
    result = img.copy()

    for idx, name in enumerate(("red", "green", "blue")):
        ch = img[..., idx]
        cfg = _CHANNEL[name]

        p10, p50, p95 = _exposure_stats(ch)

        # Adapt shoulder: if the channel is bright (high p95), shoulder kicks in
        # earlier; if its highlights have headroom, the shoulder sits higher.
        # Reference point is 0.88 — a channel at that p95 uses the stock default.
        highlight_offset = (p95 - 0.88) * 0.18 * exposure_adaptation
        adapted_shoulder = float(np.clip(cfg["shoulder_start"] - highlight_offset, 0.45, 0.92))

        # Adapt toe: heavy shadow content (low p10) deepens the toe, matching how
        # low-exposure regions of the emulsion fall onto the steeper part of the
        # H&D toe. A high-key channel with few dark pixels gets a shallower toe.
        shadow_offset = np.clip((0.08 - p10) / 0.08, -0.5, 1.0) * 0.6 * exposure_adaptation
        adapted_toe = float(cfg["toe_depth"] * (1.0 + shadow_offset))

        # Adapt gamma from the channel's median exposure. A channel whose median
        # sits above the neutral midpoint is systematically brighter and gets a
        # fractionally lower gamma (less contrast roll-off in midtones), matching
        # how a well-exposed dye layer sits on the straighter part of its curve.
        gamma_shift = (p50 - 0.42) * 0.12 * exposure_adaptation
        adapted_gamma = float(np.clip(cfg["gamma"] - gamma_shift, 0.6, 1.6))

        result[..., idx] = _channel_curve(
            ch,
            toe_depth=adapted_toe,
            shoulder_start=adapted_shoulder,
            gamma=adapted_gamma,
            base_lift=cfg["base_lift"],
            shoulder_compression=shoulder_compression,
        )

    return result
