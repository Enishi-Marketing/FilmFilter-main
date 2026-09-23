"""Color shaping for restrained, emotionally believable film warmth."""

from __future__ import annotations

import numpy as np

from .tonal import blend_with_mask, luminance, smoothstep, tonal_masks


def _compress_saturation(
    image: np.ndarray,
    *,
    saturation_compression: float,
    highlight_desaturation: float,
) -> np.ndarray:
    """Reduce color purity where film and print scans tend to compress color."""
    lum = luminance(image)[..., None]
    masks = tonal_masks(lum[..., 0])
    max_channel = np.max(image, axis=-1, keepdims=True)
    clipping_pressure = smoothstep(0.68, 1.0, max_channel)

    compression = (
        masks["highlights"] * (0.55 * saturation_compression + highlight_desaturation)
        + masks["shadows"] * saturation_compression * 0.14
        + clipping_pressure * saturation_compression * 0.30
    )
    midtone_protection = masks["midtones"] * 0.28
    saturation_scale = 1.0 - np.clip(compression * (1.0 - midtone_protection), 0.0, 0.85)
    return lum + (image - lum) * saturation_scale


def _apply_cross_channel_response(
    image: np.ndarray,
    *,
    crossover_strength: float,
    shadow_color_shift: float,
    highlight_warmth: float,
) -> np.ndarray:
    """Let channels influence one another in a restrained film-stock direction."""
    strength = np.clip(crossover_strength, 0.0, 1.0)
    shadow_shift = np.clip(shadow_color_shift, -1.0, 1.0)
    if strength <= 0.0 and abs(shadow_shift) <= 1e-6:
        return image

    img = image.copy()
    masks = tonal_masks(img)
    lum = luminance(img)[..., None]
    r = img[..., 0:1]
    g = img[..., 1:2]
    b = img[..., 2:3]

    # A tiny non-orthogonal matrix makes colors interact before selective rolloff.
    # Cyan dye (red channel) bleeds most heavily into green — the dominant real-film
    # impurity. Magenta dye (green) absorbs into blue. Yellow dye is the cleanest.
    mixed = np.empty_like(img)
    mixed[..., 0:1] = r + (g - b) * 0.060 * strength
    mixed[..., 1:2] = g + (r - g) * 0.032 * strength + (b - g) * 0.025 * strength
    mixed[..., 2:3] = b + (g - r) * 0.045 * strength
    img = img * (1.0 - strength * 0.42) + mixed * (strength * 0.42)

    r = img[..., 0:1]
    g = img[..., 1:2]
    b = img[..., 2:3]
    max_gb = np.maximum(g, b)
    red_excess = np.clip(r - max_gb, 0.0, 1.0)
    red_pressure = smoothstep(0.66, 0.98, r)
    img[..., 0:1] -= red_excess * red_pressure * masks["highlights"] * strength * 0.22
    img[..., 1:2] += red_excess * red_pressure * masks["highlights"] * strength * 0.045

    green_dominance = np.clip(g - np.maximum(r, b), 0.0, 1.0)
    olive = img.copy()
    olive[..., 0:1] += green_dominance * strength * 0.12
    olive[..., 1:2] -= green_dominance * strength * 0.16
    olive[..., 2:3] -= green_dominance * strength * 0.055
    img = blend_with_mask(img, olive, masks["midtones"] + masks["highlights"] * 0.35, strength=0.75)

    blue_dominance = np.clip(b - np.maximum(r, g), 0.0, 1.0)
    blue_compressed = lum + (img - lum) * (1.0 - blue_dominance * masks["shadows"] * strength * 0.55)
    img = blend_with_mask(img, blue_compressed, masks["shadows"], strength=0.62)

    # Shadow colour bias: positive shadow_shift → warm/amber (Kodak orange base);
    # negative shadow_shift → cool/teal (Fuji crossover). The direction vectors
    # match the actual dye-layer characteristics of each film family.
    if shadow_shift >= 0:
        shadow_bias = np.array([0.012, 0.004, -0.009], dtype=np.float32) * shadow_shift
    else:
        shadow_bias = np.array([-0.010, 0.006, 0.012], dtype=np.float32) * abs(shadow_shift)
    img += masks["shadows"] * shadow_bias * (0.45 + strength * 0.55)

    cream = np.array([1.0, 0.935, 0.825], dtype=np.float32)
    highlight_pressure = masks["highlights"] * smoothstep(0.72, 1.0, np.max(img, axis=-1, keepdims=True))
    cream_mix = highlight_pressure * (highlight_warmth * 0.85 + strength * 0.030)
    img = img * (1.0 - cream_mix) + lum * cream * cream_mix

    return img


def _apply_blue_response(
    image: np.ndarray,
    *,
    blue_desaturation: float,
) -> np.ndarray:
    """Model the yellow dye layer's characteristic compression of saturated blues.

    The yellow dye layer (which controls the blue channel) has the earliest
    highlight shoulder (0.73) and deepest shadow toe of the three dye layers.
    In practice this means saturated blues desaturate toward cyan in midtones
    and highlights — blue compresses before green, leaving a relative green
    excess that the eye reads as cyan. The effect scales with three factors:

    - Blue dominance: how far blue leads red and green in the pixel
    - Saturation: near-neutral blues (overcast sky, grey-blue surfaces) are
      left mostly alone; only chromatically committed blues are affected
    - Luminance: shadows are already handled by the per-channel curve toe so
      the effect fades in above the shadow range and strengthens as the blue
      channel approaches its shoulder point (~0.73), where compression is steepest
    """
    img = image.copy()
    r = img[..., 0:1]
    g = img[..., 1:2]
    b = img[..., 2:3]
    lum = luminance(img)[..., None]

    # How decisively blue leads both other channels.
    blue_lead = np.clip(b - np.maximum(r, g) * 0.90, 0.0, 1.0)

    # Only affect chromatically committed blues — leave near-neutral surfaces alone.
    chroma = np.max(img, axis=-1, keepdims=True) - np.min(img, axis=-1, keepdims=True)
    sat_gate = smoothstep(0.06, 0.28, chroma)

    # Luminance curve: roll in above shadows (curves handles the toe), peak in
    # midtones, then fade out toward bright sky luminance. Sky lives at high
    # luminance — we do not want to desaturate it here; the sky teal pass handles
    # sky hue. Jeans, cars, and signs live in the 0.15–0.55 luminance band.
    shadow_rolloff = smoothstep(0.10, 0.38, lum)
    sky_rolloff = 1.0 - smoothstep(0.48, 0.72, lum)
    shoulder_pressure = smoothstep(0.38, 0.68, b) * sky_rolloff
    lum_weight = shadow_rolloff * sky_rolloff * (1.0 + shoulder_pressure * 0.70)

    blue_mask = blue_lead * sat_gate * np.clip(lum_weight, 0.0, 1.8)
    strength = np.clip(blue_desaturation, 0.0, 1.0)

    # Pull blue toward luminance. The pull fraction increases near the shoulder,
    # matching how the yellow dye compresses faster than the other layers there.
    pull_fraction = strength * 0.38 * (1.0 + shoulder_pressure * 0.50)
    img[..., 2:3] = b - blue_mask * (b - lum) * np.clip(pull_fraction, 0.0, 0.80)

    # Cyan lean: as blue compresses, the retained green reads as a slight cyan cast.
    # This is the perceptual signature of the yellow dye's spectral impurity —
    # it absorbs slightly into the green band, leaving green relatively elevated.
    img[..., 1:2] = g + blue_mask * blue_lead * strength * 0.040
    img[..., 0:1] = r - blue_mask * blue_lead * strength * 0.016

    return np.clip(img, 0.0, 1.0)



def _apply_film_gamut(
    image: np.ndarray,
    *,
    gamut_compression: float,
) -> np.ndarray:
    """Hue-dependent gamut compression matching C-41 negative film.

    Color negative film cannot reproduce the full sRGB gamut. Saturated colors
    desaturate AND shift hue at the gamut boundary in characteristic ways:

    - Saturated reds (LED taillights, deep flowers) → desaturate and shift toward
      orange — the cyan dye layer cannot absorb deeply enough at the red end
    - Saturated blues (neon signs, pool water) → desaturate and shift toward cyan;
      the yellow dye layer shoulders before the others
    - Saturated greens → desaturate and shift toward yellow as the magenta dye's
      sideband absorption pulls the rendered hue warmer
    - Cyans → film's narrowest gamut region, strong compression
    - Magentas/purples → desaturate and shift toward red; film struggles to keep
      the blue contribution intact at high chroma

    Each hue region gets a soft compression of its excess-over-luminance plus a
    small additive shift in the direction the dye chemistry actually drifts.
    The pass is gated by chroma so only saturated pixels move.
    """
    if gamut_compression <= 0.0:
        return image

    img = image.copy()
    r = img[..., 0:1]
    g = img[..., 1:2]
    b = img[..., 2:3]
    lum = luminance(img)[..., None]
    strength = np.clip(gamut_compression, 0.0, 1.0)

    chroma = np.max(img, axis=-1, keepdims=True) - np.min(img, axis=-1, keepdims=True)
    # Only act on chromatically committed pixels — leave near-neutrals alone.
    sat_gate = smoothstep(0.20, 0.55, chroma)

    # Hue-region soft masks: each is the excess of its defining channel(s)
    # over the others, clipped to [0,1]. The masks overlap softly near hue
    # transitions, which is desirable — colors at hue boundaries get blended
    # treatment rather than a hard region switch.
    red_lead = np.clip(r - np.maximum(g, b), 0.0, 1.0)
    green_lead = np.clip(g - np.maximum(r, b), 0.0, 1.0)
    blue_lead = np.clip(b - np.maximum(r, g), 0.0, 1.0)
    cyan_lead = np.clip(np.minimum(g, b) - r, 0.0, 1.0)
    magenta_lead = np.clip(np.minimum(r, b) - g, 0.0, 1.0)

    # Saturated red → desaturate red toward lum, raise green for the orange shift.
    red_press = red_lead * sat_gate * strength
    img[..., 0:1] -= red_press * (r - lum) * 0.18
    img[..., 1:2] += red_press * 0.045

    # Saturated blue → desaturate blue toward lum, raise green slightly (cyan lean).
    blue_press = blue_lead * sat_gate * strength
    img[..., 2:3] -= blue_press * (b - lum) * 0.22
    img[..., 1:2] += blue_press * 0.028

    # Saturated green → desaturate green toward lum, raise red (yellow-green lean).
    green_press = green_lead * sat_gate * strength
    img[..., 1:2] -= green_press * (g - lum) * 0.18
    img[..., 0:1] += green_press * 0.028

    # Cyan → film's narrowest region; compress both contributing channels and add a
    # faint green lean (cyans render slightly green-ish on most consumer stocks).
    cyan_press = cyan_lead * sat_gate * strength
    img[..., 1:2] -= cyan_press * (g - lum) * 0.20
    img[..., 2:3] -= cyan_press * (b - lum) * 0.24
    img[..., 1:2] += cyan_press * 0.012

    # Magenta/purple → other narrow region; pull the blue contribution in harder
    # than the red, which drifts the hue toward red/pink as chroma rises.
    magenta_press = magenta_lead * sat_gate * strength
    img[..., 0:1] -= magenta_press * (r - lum) * 0.10
    img[..., 2:3] -= magenta_press * (b - lum) * 0.28

    return img


def apply_color(
    image: np.ndarray,
    *,
    saturation: float = 0.93,
    green_mute: float = 0.09,
    highlight_warmth: float = 0.045,
    skin_magenta_bias: float = 0.018,
    saturation_compression: float = 0.22,
    highlight_desaturation: float = 0.10,
    shadow_color_shift: float = 0.28,
    crossover_strength: float = 0.34,
    blue_sky_teal: float = 0.35,
    blue_desaturation: float = 0.0,
    gamut_compression: float = 0.55,
) -> np.ndarray:
    """Apply subtle cross-channel consumer-film color rendering.

    The target look favors warm, forgiving highlights, less electronic-looking
    greens, nonlinear saturation, and a tiny magenta nudge in likely skin ranges.
    Film and print scans do not behave like isolated RGB sliders: dye layers,
    exposure density, paper response, and scanning all let channels contaminate
    and compress each other. These small interactions make bright colors pastelize
    near clipping, cool shadows feel slightly impure, and foliage drift toward
    olive without turning the image into a visible cinematic grade.
    """
    img = np.clip(image.astype(np.float32, copy=False), 0.0, 1.0)
    lum = luminance(img)[..., None]

    # Restrain saturation around luminance to reduce digital harshness.
    img = lum + (img - lum) * saturation
    img = _apply_cross_channel_response(
        img,
        crossover_strength=crossover_strength,
        shadow_color_shift=shadow_color_shift,
        highlight_warmth=highlight_warmth,
    )
    img = _compress_saturation(
        img,
        saturation_compression=saturation_compression,
        highlight_desaturation=highlight_desaturation,
    )

    r = img[..., 0]
    g = img[..., 1]
    b = img[..., 2]

    # Mute saturated green/yellow-green foliage without turning it gray.
    green_dominance = np.clip(g - np.maximum(r, b), 0.0, 1.0)
    img[..., 1] -= green_dominance * green_mute
    img[..., 0] += green_dominance * green_mute * 0.20

    # Warm midtone subjects — buildings, skin, warm-lit surfaces. Bell-shaped mask
    # peaks around lum 0.50 and fades before sky luminance (~0.72+) so bright
    # neutral subjects like blue sky are not pulled warm by this pass. The cream
    # blend in _apply_cross_channel_response handles highlight warmth separately.
    high_mask = smoothstep(0.22, 0.62, lum) * (1.0 - smoothstep(0.55, 0.82, lum))
    img[..., 0] += high_mask[..., 0] * highlight_warmth
    img[..., 2] -= high_mask[..., 0] * highlight_warmth * 0.45

    # Approximate a skin-friendly region and bias it gently toward magenta.
    skin_luma = luminance(img)
    skin_mask = (
        (r > g * 0.95)
        & (r > b * 1.05)
        & (g > b * 0.85)
        & (skin_luma > 0.22)
        & (skin_luma < 0.82)
    ).astype(np.float32)[..., None]
    img[..., 0] += skin_mask[..., 0] * skin_magenta_bias
    img[..., 1] -= skin_mask[..., 0] * skin_magenta_bias * 0.35
    img[..., 2] += skin_mask[..., 0] * skin_magenta_bias * 0.35

    # Hue-selective blue compression matching the yellow dye layer's response.
    if blue_desaturation > 0.0:
        img = _apply_blue_response(img, blue_desaturation=blue_desaturation)

    # Hue-dependent gamut compression for colors outside C-41's reachable range.
    # Runs before the sky teal and white-approach passes so those hue-specific
    # shifts layer on a gamut-realistic foundation rather than fighting it.
    if gamut_compression > 0.0:
        img = _apply_film_gamut(img, gamut_compression=gamut_compression)

    # Blue-sky teal shift: blue-dominant mid-bright pixels with meaningful
    # saturation drift toward cyan-teal, matching the characteristic rendering
    # of the cyan dye layer in areas where red exposure was low.
    if blue_sky_teal > 0.0:
        r_now = img[..., 0:1]
        g_now = img[..., 1:2]
        b_now = img[..., 2:3]
        lum_now = luminance(img)[..., None]
        blue_lead = np.clip(b_now - np.maximum(r_now, g_now) * 0.88, 0.0, 1.0)
        saturation_now = np.max(img, axis=-1, keepdims=True) - np.min(img, axis=-1, keepdims=True)
        sky_lum_weight = smoothstep(0.18, 0.45, lum_now) * (1.0 - smoothstep(0.72, 0.95, lum_now))
        sky_mask = blue_lead * smoothstep(0.04, 0.28, saturation_now) * sky_lum_weight
        teal_strength = np.clip(blue_sky_teal, 0.0, 1.0)
        img[..., 1:2] += sky_mask * teal_strength * 0.052
        img[..., 0:1] -= sky_mask * teal_strength * 0.028

    # Approaching-white highlight: the blue dye channel shoulders earliest so very
    # bright values shift faintly yellow-green before paper white, rather than
    # desaturating straight to neutral as digital sensors do.
    lum_final = luminance(img)[..., None]
    white_approach = smoothstep(0.78, 0.96, lum_final)
    img[..., 0:1] += white_approach * 0.014
    img[..., 1:2] += white_approach * 0.009
    img[..., 2:3] -= white_approach * 0.024

    # Shadow chroma ceiling: film at very low exposure has almost no colour
    # discrimination — dye density differences collapse toward the neutral
    # density floor. The ceiling scales as lum² so near-black pixels carry
    # only a trace of colour (ceiling ≈ 0.03 at lum 0.07) while midtones
    # (lum ≥ 0.40) are completely unrestricted. This eliminates electric-blue
    # or electric-red blobs from saturated objects (car bodies, clothing) that
    # happen to be in shadow, without affecting the warm Kodak amber cast which
    # lives at chroma values too small to be clipped by this formula.
    lum_shadow = luminance(img)[..., None]
    chroma_now = np.max(img, axis=-1, keepdims=True) - np.min(img, axis=-1, keepdims=True)
    chroma_ceiling = np.clip((lum_shadow / 0.40) ** 2.0, 0.04, 1.0)
    chroma_scale = np.minimum(chroma_ceiling / np.maximum(chroma_now, 1e-6), 1.0)
    img = lum_shadow + (img - lum_shadow) * chroma_scale

    return np.clip(img, 0.0, 1.0)
