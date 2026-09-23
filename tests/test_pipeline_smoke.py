"""Smoke tests for the first FilmFilter pipeline foundation."""

from __future__ import annotations

import numpy as np

from pipeline.color import apply_color
from pipeline.exposure import apply_exposure
from pipeline.grain import apply_grain
from pipeline.pipeline import FilmPipeline, load_preset
from pipeline.tonal import tonal_masks, visualize_masks


def test_soft_portrait_pipeline_runs_on_float_rgb_image() -> None:
    preset = load_preset("kodak_prima_400")
    preset["effects"]["grain"]["seed"] = 123
    pipeline = FilmPipeline(preset)

    gradient = np.linspace(0.0, 1.0, 32, dtype=np.float32)
    x, y = np.meshgrid(gradient, gradient, indexing="xy")
    image = np.dstack((x, y, np.full((32, 32), 0.45, dtype=np.float32)))

    output = pipeline.process(image)

    assert output.shape == image.shape
    assert np.isfinite(output).all()
    assert output.min() >= 0.0
    assert output.max() <= 1.0
    assert not np.allclose(output, image)


def test_exposure_stage_uses_photographic_stops() -> None:
    image = np.array(
        [
            [[0.10, 0.25, 0.50], [0.40, 0.60, 0.90]],
            [[0.02, 0.18, 0.72], [0.33, 0.44, 0.55]],
        ],
        dtype=np.float32,
    )

    neutral = apply_exposure(image, exposure=0.0)
    brighter = apply_exposure(image, exposure=1.0)
    darker = apply_exposure(image, exposure=-1.0)

    assert np.allclose(neutral, image)
    assert np.allclose(brighter, np.clip(image * 2.0, 0.0, 1.0))
    assert np.allclose(darker, image * 0.5)
    assert np.isfinite(brighter).all()
    assert brighter.min() >= 0.0
    assert brighter.max() <= 1.0


def test_tonal_masks_overlap_smoothly() -> None:
    gradient = np.linspace(0.0, 1.0, 64, dtype=np.float32)
    masks = tonal_masks(gradient)
    preview = visualize_masks(masks)

    assert set(masks) == {"shadows", "midtones", "highlights"}
    assert masks["shadows"].shape == (64, 1)
    assert masks["midtones"].shape == (64, 1)
    assert masks["highlights"].shape == (64, 1)
    assert preview.shape == (64, 3)
    assert np.isfinite(preview).all()
    assert masks["shadows"][20, 0] > 0.0
    assert masks["midtones"][20, 0] > 0.0
    assert masks["midtones"][44, 0] > 0.0
    assert masks["highlights"][44, 0] > 0.0


def test_color_stage_compresses_bright_saturation_more_than_midtones() -> None:
    image = np.array(
        [
            [[0.62, 0.34, 0.30], [0.98, 0.22, 0.18]],
            [[0.22, 0.24, 0.44], [0.30, 0.60, 0.25]],
        ],
        dtype=np.float32,
    )

    output = apply_color(
        image,
        saturation=1.0,
        green_mute=0.0,
        highlight_warmth=0.0,
        skin_magenta_bias=0.0,
        saturation_compression=0.45,
        highlight_desaturation=0.20,
        shadow_color_shift=0.0,
        crossover_strength=0.25,
    )

    input_chroma = np.max(image, axis=-1) - np.min(image, axis=-1)
    output_chroma = np.max(output, axis=-1) - np.min(output, axis=-1)

    assert output.shape == image.shape
    assert np.isfinite(output).all()
    assert output.min() >= 0.0
    assert output.max() <= 1.0
    assert output_chroma[0, 1] < input_chroma[0, 1]
    assert (input_chroma[0, 0] - output_chroma[0, 0]) < (input_chroma[0, 1] - output_chroma[0, 1])


def test_grain_stage_media_texture_is_deterministic_and_bounded() -> None:
    gradient = np.linspace(0.02, 0.98, 40, dtype=np.float32)
    x, y = np.meshgrid(gradient, gradient, indexing="xy")
    image = np.dstack((x, y * 0.82 + 0.08, np.full((40, 40), 0.36, dtype=np.float32)))

    kwargs = {
        "grain_amount": 0.024,
        "micro_grain_amount": 0.017,
        "mid_grain_amount": 0.007,
        "density_variation_amount": 0.003,
        "scanner_softness": 0.045,
        "tonal_diffusion": 0.035,
        "edge_softening": 0.035,
        "chroma_instability": 0.014,
        "density_instability": 0.010,
        "scan_irregularity": 0.010,
        "seed": 321,
    }

    first = apply_grain(image, **kwargs)
    second = apply_grain(image, **kwargs)

    assert first.shape == image.shape
    assert np.isfinite(first).all()
    assert first.min() >= 0.0
    assert first.max() <= 1.0
    assert np.allclose(first, second)
    assert not np.allclose(first, image)
