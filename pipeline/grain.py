"""Procedural media texture for believable scanned-print rendering."""

from __future__ import annotations

import cv2
import numpy as np

from .tonal import luminance, smoothstep, tonal_masks


def apply_grain(
    image: np.ndarray,
    *,
    grain_amount: float = 0.024,
    grain_size: float = 1.45,
    grain_shadow_bias: float = 0.58,
    grain_chromaticity: float = 0.18,
    micro_grain_amount: float = 0.018,
    mid_grain_amount: float = 0.008,
    density_variation_amount: float = 0.004,
    clump_amount: float = 0.55,
    size_variation: float = 0.45,
    grain_softness: float = 0.45,
    texture_scale_balance: float = 0.48,
    scanner_softness: float = 0.05,
    tonal_diffusion: float = 0.04,
    edge_softening: float = 0.04,
    chroma_instability: float = 0.018,
    density_instability: float = 0.012,
    scan_irregularity: float = 0.012,
    strength: float | None = None,
    size: float | None = None,
    chroma: float | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """Render image content through layered photographic media texture.

    Scanned consumer film rarely separates clean image structure from texture.
    Grain, paper density, scanner softness, shadow impurity, and tiny alignment
    errors all interact at low strength. This stage keeps those cues subtle by
    layering micro grain, mid-frequency texture, and extremely low-frequency
    density variation, then coupling them to luminance, local contrast, color
    purity, and edge transitions. The intent is not visible damage or retro
    spectacle; it is a quieter sense that the picture passed through a physical
    medium before becoming pixels.
    """
    img = np.clip(image.astype(np.float32, copy=False), 0.0, 1.0)
    h, w = img.shape[:2]
    rng = np.random.default_rng(seed)

    # Accept the first-pass names so older presets remain usable.
    if strength is not None:
        grain_amount = strength
    if size is not None:
        grain_size = size
    if chroma is not None:
        grain_chromaticity = chroma

    def normalized_map(values: np.ndarray) -> np.ndarray:
        values = values - float(np.mean(values))
        return values / max(float(np.std(values)), 1e-6)

    def normalized_noise(shape: tuple[int, ...], sigma: float) -> np.ndarray:
        noise = rng.normal(0.0, 1.0, shape).astype(np.float32)
        if sigma > 0.01:
            noise = cv2.GaussianBlur(noise, ksize=(0, 0), sigmaX=sigma, sigmaY=sigma)
            if noise.ndim == 2:
                noise = noise[..., None]
        return normalized_map(noise)

    def heavy_tail_noise(shape: tuple[int, ...], sigma: float, variation: float) -> np.ndarray:
        """Noise with non-Gaussian tails — produces occasional larger 'kernels'.

        Real emulsion crystals follow a roughly log-normal size distribution.
        We approximate this by blending a Gaussian field with a sparser, sharper
        field that has been raised to a power preserving sign. The result keeps
        the same statistics on average but has heavier tails: a few grains pop
        noticeably bigger and brighter than the rest.
        """
        base = normalized_noise(shape, sigma)
        if variation <= 0.0:
            return base
        coarse = normalized_noise(shape, sigma * 1.85)
        sign = np.sign(coarse)
        accent = sign * np.abs(coarse) ** 0.55
        accent = normalized_map(accent)
        mix = np.clip(variation, 0.0, 1.0)
        return normalized_map(base * (1.0 - mix * 0.55) + accent * (mix * 0.55))

    def shift_channel(channel: np.ndarray, shift_x: float, shift_y: float) -> np.ndarray:
        matrix = np.float32([[1, 0, shift_x], [0, 1, shift_y]])
        return cv2.warpAffine(channel, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

    luminance_values = luminance(img)[..., None]
    masks = tonal_masks(luminance_values[..., 0])
    lum2d = luminance_values[..., 0]

    local_luma = cv2.GaussianBlur(lum2d, ksize=(0, 0), sigmaX=1.05, sigmaY=1.05)
    local_contrast = np.abs(lum2d - local_luma)[..., None]
    edge_map = smoothstep(0.018, 0.105, local_contrast)
    harsh_edge = smoothstep(0.035, 0.14, local_contrast)

    balance = np.clip(texture_scale_balance, 0.0, 1.0)
    variation = np.clip(size_variation, 0.0, 1.0)
    micro = heavy_tail_noise((h, w, 1), max(float(grain_size) * 0.20, 0.01), variation)
    fine = heavy_tail_noise((h, w, 1), max(float(grain_size) * 0.42, 0.01), variation * 0.85)
    mid = normalized_noise((h, w, 1), max(float(grain_size) * (1.15 + balance * 1.10), 0.01))
    low = normalized_noise((h, w, 1), max(min(h, w) * (0.038 + balance * 0.030), 1.8))

    # Clump field: intermediate-scale density modulation that creates the
    # darker patches characteristic of real emulsion. Sized in pixels relative
    # to grain_size so clumps scale with kernel size.
    clump_sigma = max(float(grain_size) * 6.0 + 4.0, 3.0)
    clump_field = normalized_noise((h, w, 1), clump_sigma)
    clump_mod = clump_field * np.clip(clump_amount, 0.0, 1.0) * 0.55

    micro_layer = normalized_map(micro * 0.72 + fine * 0.28)
    mid_layer = normalized_map(mid * 0.78 + fine * 0.22)
    density_layer = normalized_map(low)
    # Modulate fine-scale grain energy by the clump field: regions where the
    # clump field is high get amplified grain, low regions get suppressed.
    clump_envelope = 1.0 + clump_mod
    micro_layer = micro_layer * clump_envelope
    mid_layer = mid_layer * (1.0 + clump_mod * 0.55)
    mono_grain = normalized_map(
        micro_layer * (0.70 - balance * 0.18)
        + mid_layer * (0.20 + balance * 0.22)
        + density_layer * (0.05 + balance * 0.02)
    )

    # Dye cloud sizes differ per layer: yellow (blue ch) is coarsest, magenta
    # (green ch) is finest, cyan (red ch) is intermediate. Generate independent
    # per-channel noise at layer-appropriate blur radii so chroma grain has the
    # correct frequency character rather than uniform cross-channel texture.
    _ch_scale = [1.00, 0.72, 1.40]  # red, green, blue — relative to grain_size
    color_grain = np.empty((h, w, 3), dtype=np.float32)
    for ci, scale in enumerate(_ch_scale):
        fine_ch = heavy_tail_noise((h, w), max(float(grain_size) * 0.22 * scale, 0.01), variation * 0.7)
        med_ch = normalized_noise((h, w), max(float(grain_size) * 0.85 * scale, 0.01))
        ch = normalized_map(fine_ch * 0.66 + med_ch * 0.34)
        color_grain[..., ci : ci + 1] = ch * clump_envelope

    # Texture is exposure-aware and edge-aware. Highlights remain creamy, while
    # hard digital transitions get less additive grain and more soft integration.
    shadow_weight = (1.0 - luminance_values) ** (1.15 + np.clip(grain_shadow_bias, 0.0, 1.0) * 0.85)
    mid_weight = masks["midtones"] * 0.62 + np.exp(-((luminance_values - 0.42) ** 2) / 0.08) * 0.38
    highlight_protection = 1.0 - masks["highlights"] * 0.78
    contrast_texture = 1.0 + smoothstep(0.004, 0.05, local_contrast) * 0.16
    edge_attenuation = 1.0 - edge_map * np.clip(edge_softening, 0.0, 1.0) * 0.48
    intensity = (0.30 + shadow_weight * 0.62 + mid_weight * 0.32) * highlight_protection
    intensity = intensity * contrast_texture * edge_attenuation

    chroma_mix = np.clip(grain_chromaticity, 0.0, 1.0)
    micro_strength = np.clip(micro_grain_amount, 0.0, 0.12)
    mid_strength = np.clip(mid_grain_amount, 0.0, 0.08)
    density_strength = np.clip(density_variation_amount, 0.0, 0.04)
    legacy_strength = np.clip(grain_amount, 0.0, 0.20)

    luma_texture = (
        micro_layer * micro_strength
        + mid_layer * mid_strength * (0.72 + masks["shadows"] * 0.22)
        + mono_grain * legacy_strength * 0.55
    )
    chroma_texture = color_grain * (legacy_strength * chroma_mix * 0.70 + micro_strength * chroma_mix * 0.20)
    # Colour grain in near-black areas creates visible per-channel blobs: each
    # dye-layer noise pattern is independent so a dark pixel gets pushed red, blue,
    # or green by whichever channel happened to be high at that spot. Real film has
    # no dye density to modulate at very low exposure, so fade the colour grain
    # contribution to zero below a meaningful signal floor. Luma grain is unaffected
    # — silver grain in shadows is expected and looks correct.
    chroma_signal_gate = smoothstep(0.06, 0.35, luminance_values)
    grain = (luma_texture * (1.0 - chroma_mix * 0.38) + chroma_texture * chroma_signal_gate) * intensity

    # Optical integration: scanned grain is never razor-sharp. A small Gaussian
    # blur on the assembled grain layer fuses adjacent kernels into the soft,
    # slightly diffused appearance of real emulsion under a scanner's sample
    # aperture. Without this, multi-octave noise reads as crisp digital dither.
    soft_grain = np.clip(grain_softness, 0.0, 1.0)
    if soft_grain > 0.0:
        blur_sigma = 0.35 + soft_grain * 0.65
        grain = cv2.GaussianBlur(grain, ksize=(0, 0), sigmaX=blur_sigma, sigmaY=blur_sigma)
        if grain.ndim == 2:
            grain = grain[..., None]

    density_amount = np.clip(density_instability, 0.0, 0.08) + density_strength
    density_modulation = density_layer * density_amount * (
        0.42 + masks["shadows"] * 0.36 + masks["midtones"] * 0.18
    )
    img = img * (1.0 + density_modulation)
    img = img + grain

    # Shadow density on print scans has a soft floor and slight color impurity.
    # Keep the contamination weak and red/yellow-biased enough to avoid teal mud.
    shadow_texture = normalized_map(density_layer * 0.70 + mid_layer * 0.30)
    shadow_mask = masks["shadows"] * (1.0 - smoothstep(0.12, 0.46, luminance_values))
    soft_floor = shadow_mask * (0.0035 + density_amount * 0.020) * (1.0 + shadow_texture * 0.18)
    contamination = np.array([0.006, 0.0015, -0.0035], dtype=np.float32)
    img = img + soft_floor + shadow_mask * shadow_texture * contamination * (0.32 + chroma_mix * 0.24)

    # Scanner-like softness is frequency-selective. It trims brittle precision
    # and lets texture participate in transitions without creating global haze.
    soft = np.clip(scanner_softness, 0.0, 1.0)
    diffusion = np.clip(tonal_diffusion, 0.0, 1.0)
    edge_soft = np.clip(edge_softening, 0.0, 1.0)
    if soft > 0.0 or diffusion > 0.0 or edge_soft > 0.0:
        bilateral = cv2.bilateralFilter(
            np.clip(img, 0.0, 1.0).astype(np.float32),
            d=0,
            sigmaColor=0.010 + diffusion * 0.045,
            sigmaSpace=0.65 + soft * 1.35,
        )
        gaussian = cv2.GaussianBlur(img, ksize=(0, 0), sigmaX=0.42 + soft * 0.52, sigmaY=0.42 + soft * 0.52)
        small_detail = img - gaussian
        detail_scale = 1.0 - (0.10 * soft + 0.08 * diffusion) * (1.0 - masks["highlights"] * 0.35)
        detail_softened = gaussian + small_detail * detail_scale
        edge_mix = harsh_edge * edge_soft * 0.22 + masks["midtones"] * diffusion * 0.055
        img = detail_softened * (1.0 - edge_mix) + bilateral * edge_mix

    # Texture slightly breaks digital color purity. The modulation is strongest
    # outside likely skin ranges and fades in highlights to preserve natural faces.
    lum_after = luminance(np.clip(img, 0.0, 1.0))[..., None]
    chroma_delta = img - lum_after
    color_purity = (np.max(img, axis=-1, keepdims=True) - np.min(img, axis=-1, keepdims=True))
    r = img[..., 0:1]
    g = img[..., 1:2]
    b = img[..., 2:3]
    skin_like = (
        (r > g * 0.94)
        & (r > b * 1.04)
        & (g > b * 0.82)
        & (lum_after > 0.22)
        & (lum_after < 0.84)
    ).astype(np.float32)
    texture_chroma = np.clip(chroma_instability, 0.0, 0.12)
    saturation_mod = 1.0 + density_layer * texture_chroma * color_purity * (1.0 - masks["highlights"] * 0.70)
    saturation_mod -= mid_layer * texture_chroma * 0.22 * (1.0 - skin_like * 0.72)
    # Near-black pixels have no meaningful dye density to modulate. Fade the
    # saturation modulation to zero below a meaningful signal floor so the grain
    # stage does not amplify faint colour casts in near-black areas.
    shadow_sat_gate = smoothstep(0.04, 0.25, lum_after)
    saturation_mod = 1.0 + (saturation_mod - 1.0) * shadow_sat_gate
    img = lum_after + chroma_delta * saturation_mod

    if texture_chroma > 0.0:
        drift_px = texture_chroma * 0.42
        drifted = img.copy()
        drifted[..., 0] = shift_channel(img[..., 0], drift_px, -drift_px * 0.35)
        drifted[..., 2] = shift_channel(img[..., 2], -drift_px * 0.55, drift_px * 0.25)
        # Knee on signal level: real dye misregistration is invisible near black
        # because there is no density to displace. Fade the blend to zero below
        # a meaningful signal floor so near-black pixels keep their channel alignment.
        signal_floor = smoothstep(0.04, 0.28, luminance_values)
        chroma_mask = (masks["shadows"] * 0.55 + masks["midtones"] * 0.28) * (1.0 - skin_like * 0.62) * signal_floor
        img = img * (1.0 - chroma_mask * texture_chroma * 0.60) + drifted * (chroma_mask * texture_chroma * 0.60)

    irregularity = np.clip(scan_irregularity, 0.0, 0.10)
    if irregularity > 0.0:
        x_grid, y_grid = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        dx = normalized_noise((h, w, 1), max(min(h, w) * 0.055, 2.0))[..., 0] * irregularity * 0.24
        dy = normalized_noise((h, w, 1), max(min(h, w) * 0.075, 2.0))[..., 0] * irregularity * 0.14
        img = cv2.remap(
            img.astype(np.float32),
            (x_grid + dx).astype(np.float32),
            (y_grid + dy).astype(np.float32),
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )

    return np.clip(img, 0.0, 1.0).astype(np.float32)
