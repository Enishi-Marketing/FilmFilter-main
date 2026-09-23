"""Optional scan/camera light leak simulation.

Light leaks are warm, soft gradients that bleed in from the edge of the frame
when stray light reaches the film between exposures or during loading. They are
characteristically:

- Edge-anchored, often strongest at one side or corner
- Warm-biased (orange / red / amber), occasionally yellow
- Soft-edged with low-frequency irregularity — not a clean gradient
- Roughly additive in highlights, less visible in shadows

This stage is intentionally off-by-default and only runs if the preset opts in
by adding ``"light_leak"`` to its pipeline list. Defaults are conservative; the
effect is easy to overdo and ages a photograph quickly.
"""

from __future__ import annotations

import cv2
import numpy as np


def apply_light_leak(
    image: np.ndarray,
    *,
    amount: float = 0.18,
    position: str = "right",
    color: tuple[float, float, float] = (1.00, 0.55, 0.20),
    coverage: float = 0.35,
    softness: float = 0.55,
    irregularity: float = 0.30,
    highlight_bias: float = 0.55,
    seed: int | None = None,
) -> np.ndarray:
    """Bleed a warm, soft light leak in from the frame edge.

    Parameters
    ----------
    amount:
        Peak intensity of the leak (0..1). Around 0.15-0.25 reads as believable;
        above 0.4 the image starts to look stylised.
    position:
        Which side or corner the leak originates from. One of: ``"left"``,
        ``"right"``, ``"top"``, ``"bottom"``, ``"top-left"``, ``"top-right"``,
        ``"bottom-left"``, ``"bottom-right"``.
    color:
        RGB tint of the leak. Defaults to a warm orange. Use ``(1.0, 0.85, 0.55)``
        for a softer amber or ``(1.0, 0.35, 0.30)`` for a redder leak.
    coverage:
        How far into the frame the leak reaches as a fraction of the frame's
        short edge (0..1). Larger values produce a broader wash.
    softness:
        Smoothness of the falloff curve. 0 gives a relatively sharp edge,
        1 gives a long, diffuse gradient.
    irregularity:
        Amount of low-frequency noise modulating the leak shape so it does not
        look like a clean radial gradient.
    highlight_bias:
        How much the leak prefers existing highlights (0 = uniform additive,
        1 = strongly favours bright areas, screen-blend-like).
    seed:
        Optional RNG seed for reproducible irregularity.
    """
    if amount <= 0.0:
        return image

    img = np.clip(image.astype(np.float32, copy=False), 0.0, 1.0)
    h, w = img.shape[:2]

    # Compute distance from the chosen anchor, normalised to the short edge.
    yy, xx = np.meshgrid(
        np.linspace(0.0, 1.0, h, dtype=np.float32),
        np.linspace(0.0, 1.0, w, dtype=np.float32),
        indexing="ij",
    )
    anchors = {
        "left":         (0.0, 0.5, "linear_x"),
        "right":        (1.0, 0.5, "linear_x"),
        "top":          (0.5, 0.0, "linear_y"),
        "bottom":       (0.5, 1.0, "linear_y"),
        "top-left":     (0.0, 0.0, "radial"),
        "top-right":    (1.0, 0.0, "radial"),
        "bottom-left":  (0.0, 1.0, "radial"),
        "bottom-right": (1.0, 1.0, "radial"),
    }
    if position not in anchors:
        raise ValueError(f"Unknown light_leak position: {position!r}")
    ax, ay, mode = anchors[position]

    if mode == "linear_x":
        distance = np.abs(xx - ax)
    elif mode == "linear_y":
        distance = np.abs(yy - ay)
    else:  # radial corner
        distance = np.sqrt((xx - ax) ** 2 + (yy - ay) ** 2) / np.sqrt(2.0)

    # Falloff: at distance 0 we are at peak, fading to 0 by `coverage`.
    reach = max(float(coverage), 0.05)
    # Soft exponent — higher softness flattens the curve so it bleeds further.
    soft = np.clip(softness, 0.0, 1.0)
    exponent = 2.2 - soft * 1.6  # range ~0.6 (very soft) to 2.2 (sharp)
    falloff = np.clip(1.0 - distance / reach, 0.0, 1.0) ** exponent

    # Low-frequency irregularity so the leak does not read as a clean gradient.
    if irregularity > 0.0:
        rng = np.random.default_rng(seed)
        noise = rng.normal(0.0, 1.0, (h, w)).astype(np.float32)
        blur_sigma = max(min(h, w) * 0.08, 8.0)
        noise = cv2.GaussianBlur(noise, ksize=(0, 0), sigmaX=blur_sigma, sigmaY=blur_sigma)
        noise = noise - float(np.mean(noise))
        noise = noise / max(float(np.std(noise)), 1e-6)
        falloff = falloff * np.clip(1.0 + noise * np.clip(irregularity, 0.0, 1.0) * 0.55, 0.0, 1.8)

    falloff = falloff[..., None]

    # Highlight bias: blend between uniform additive and screen-blend-like.
    bias = np.clip(highlight_bias, 0.0, 1.0)
    luma = (img[..., 0:1] * 0.30 + img[..., 1:2] * 0.59 + img[..., 2:3] * 0.11)
    highlight_weight = (1.0 - bias) + bias * np.clip(luma * 1.15 + 0.15, 0.0, 1.0)

    tint = np.array(color, dtype=np.float32).reshape(1, 1, 3)
    contribution = falloff * highlight_weight * tint * np.clip(amount, 0.0, 1.0)

    # Soft-add: 1 - (1-a)(1-b). Keeps highlights from blowing out abruptly.
    out = 1.0 - (1.0 - img) * (1.0 - contribution)
    return np.clip(out, 0.0, 1.0).astype(np.float32)
