"""Declarative parameter schema for the FilmFilter editor UI.

Each stage lists the controls the editor renders. Keeping the schema declarative
means new pipeline parameters need exactly one entry here to appear in the UI,
participate in preset save/load, and round-trip through the preview renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ParamKind = Literal["float", "int", "bool", "choice", "color3"]


@dataclass(frozen=True)
class Param:
    """Definition of a single tunable parameter for the UI layer."""

    name: str
    label: str
    kind: ParamKind
    default: Any
    minimum: float | int | None = None
    maximum: float | int | None = None
    step: float | int | None = None
    choices: tuple[str, ...] | None = None
    tooltip: str = ""


@dataclass(frozen=True)
class StageSchema:
    """Schema for one pipeline stage."""

    name: str
    label: str
    enabled_default: bool = True
    params: tuple[Param, ...] = field(default_factory=tuple)


# Stage order here mirrors the canonical preset pipeline order. The UI renders
# stages in this order regardless of the order they appear inside a preset file.
SCHEMA: tuple[StageSchema, ...] = (
    StageSchema(
        name="exposure",
        label="Exposure",
        params=(
            Param("exposure", "Exposure (EV)", "float", 0.0, -5.0, 5.0, 0.01,
                  tooltip="+1 doubles brightness; -1 halves it before the film tone curve."),
        ),
    ),
    StageSchema(
        name="tone",
        label="Tone",
        params=(
            Param("black_lift", "Black lift", "float", 0.045, 0.0, 0.2, 0.001,
                  tooltip="Raise the shadow floor like print paper density."),
            Param("contrast_softness", "Contrast softness", "float", 0.18, 0.0, 1.0, 0.01),
            Param("highlight_compression", "Highlight compression", "float", 0.38, 0.0, 1.0, 0.01),
            Param("shoulder_strength", "Shoulder strength", "float", 0.42, 0.0, 1.0, 0.01),
            Param("shadow_chroma_damping", "Shadow chroma damping", "float", 0.22, 0.0, 1.0, 0.01),
            Param("rolloff_start", "Rolloff start", "float", 0.62, 0.4, 0.95, 0.01),
            Param("midtone_preservation", "Midtone preservation", "float", 0.65, 0.0, 1.0, 0.01),
        ),
    ),
    StageSchema(
        name="curves",
        label="Curves",
        params=(
            Param("exposure_adaptation", "Exposure adaptation", "float", 0.70, 0.0, 1.0, 0.01),
            Param("shoulder_compression", "Shoulder compression", "float", 0.42, 0.04, 1.0, 0.01),
        ),
    ),
    StageSchema(
        name="color",
        label="Color",
        params=(
            Param("saturation", "Saturation", "float", 0.93, 0.0, 1.5, 0.01),
            Param("green_mute", "Green mute", "float", 0.09, 0.0, 0.4, 0.005),
            Param("highlight_warmth", "Highlight warmth", "float", 0.045, 0.0, 0.2, 0.001),
            Param("skin_magenta_bias", "Skin magenta bias", "float", 0.018, 0.0, 0.1, 0.001),
            Param("saturation_compression", "Saturation compression", "float", 0.22, 0.0, 1.0, 0.01),
            Param("highlight_desaturation", "Highlight desaturation", "float", 0.10, 0.0, 0.6, 0.005),
            Param("shadow_color_shift", "Shadow color shift", "float", 0.28, -1.0, 1.0, 0.01,
                  tooltip="Positive = warm Kodak base, negative = cool Fuji crossover."),
            Param("crossover_strength", "Crossover strength", "float", 0.34, 0.0, 1.0, 0.01),
            Param("blue_sky_teal", "Blue sky teal", "float", 0.35, 0.0, 1.0, 0.01),
            Param("blue_desaturation", "Blue desaturation", "float", 0.0, 0.0, 1.0, 0.01),
            Param("gamut_compression", "Gamut compression", "float", 0.55, 0.0, 1.0, 0.01),
        ),
    ),
    StageSchema(
        name="halation",
        label="Halation",
        params=(
            Param("strength", "Strength", "float", 0.055, 0.0, 0.4, 0.001),
            Param("intensity_percent", "Intensity %", "float", 100.0, 0.0, 200.0, 1.0),
            Param("threshold", "Threshold", "float", 0.72, 0.3, 0.99, 0.01),
            Param("radius", "Radius (px)", "float", 9.0, 0.5, 40.0, 0.5),
            Param("warmth", "Warmth (R,G,B)", "color3", (1.0, 0.42, 0.18)),
        ),
    ),
    StageSchema(
        name="sharpness",
        label="Sharpness",
        params=(
            Param("soften_digital_sharpness", "Soften digital sharpness", "bool", False),
            Param("sharpness_softening_strength", "Softening strength", "float", 0.18, 0.0, 1.0, 0.01),
            Param("microcontrast_reduction", "Microcontrast reduction", "float", 0.16, 0.0, 1.0, 0.01),
        ),
    ),
    StageSchema(
        name="grain",
        label="Grain",
        params=(
            Param("grain_amount", "Grain amount", "float", 0.024, 0.0, 0.2, 0.001),
            Param("grain_size", "Grain size", "float", 1.45, 0.2, 4.0, 0.05),
            Param("grain_shadow_bias", "Shadow bias", "float", 0.58, 0.0, 1.0, 0.01),
            Param("grain_chromaticity", "Chromaticity", "float", 0.18, 0.0, 1.0, 0.01),
            Param("micro_grain_amount", "Micro grain", "float", 0.018, 0.0, 0.12, 0.001),
            Param("mid_grain_amount", "Mid grain", "float", 0.008, 0.0, 0.08, 0.001),
            Param("density_variation_amount", "Density variation", "float", 0.004, 0.0, 0.04, 0.0005),
            Param("clump_amount", "Clump amount", "float", 0.55, 0.0, 1.0, 0.01),
            Param("size_variation", "Size variation", "float", 0.45, 0.0, 1.0, 0.01),
            Param("grain_softness", "Grain softness", "float", 0.45, 0.0, 1.0, 0.01),
            Param("texture_scale_balance", "Texture balance", "float", 0.48, 0.0, 1.0, 0.01),
            Param("scanner_softness", "Scanner softness", "float", 0.05, 0.0, 1.0, 0.01),
            Param("tonal_diffusion", "Tonal diffusion", "float", 0.04, 0.0, 1.0, 0.01),
            Param("edge_softening", "Edge softening", "float", 0.04, 0.0, 1.0, 0.01),
            Param("chroma_instability", "Chroma instability", "float", 0.018, 0.0, 0.12, 0.001),
            Param("density_instability", "Density instability", "float", 0.012, 0.0, 0.08, 0.001),
            Param("scan_irregularity", "Scan irregularity", "float", 0.012, 0.0, 0.1, 0.001),
            Param("seed", "Seed (blank = random)", "int", None, 0, 999_999, 1,
                  tooltip="Leave blank for non-deterministic grain."),
        ),
    ),
    StageSchema(
        name="lens",
        label="Lens",
        params=(
            Param("vignette", "Vignette", "float", 0.10, 0.0, 1.0, 0.01),
            Param("edge_softness", "Edge softness", "float", 0.18, 0.0, 1.0, 0.01),
            Param("aberration", "Chromatic aberration", "float", 0.25, 0.0, 2.0, 0.01),
        ),
    ),
    StageSchema(
        name="light_leak",
        label="Light leak",
        enabled_default=False,
        params=(
            Param("amount", "Amount", "float", 0.18, 0.0, 1.0, 0.01),
            Param("position", "Position", "choice", "right",
                  choices=("left", "right", "top", "bottom",
                           "top-left", "top-right", "bottom-left", "bottom-right")),
            Param("color", "Color (R,G,B)", "color3", (1.00, 0.55, 0.20)),
            Param("coverage", "Coverage", "float", 0.35, 0.05, 1.0, 0.01),
            Param("softness", "Softness", "float", 0.55, 0.0, 1.0, 0.01),
            Param("irregularity", "Irregularity", "float", 0.30, 0.0, 1.0, 0.01),
            Param("highlight_bias", "Highlight bias", "float", 0.55, 0.0, 1.0, 0.01),
            Param("seed", "Seed (blank = random)", "int", None, 0, 999_999, 1),
        ),
    ),
)


STAGE_ORDER: tuple[str, ...] = tuple(stage.name for stage in SCHEMA)
STAGE_BY_NAME: dict[str, StageSchema] = {stage.name: stage for stage in SCHEMA}


def stage_defaults(stage_name: str) -> dict[str, Any]:
    """Return the default ``effects`` block (including ``enabled``) for a stage."""
    stage = STAGE_BY_NAME[stage_name]
    block: dict[str, Any] = {"enabled": stage.enabled_default}
    for param in stage.params:
        block[param.name] = param.default
    return block


def default_preset() -> dict[str, Any]:
    """Return a fully-populated preset using every stage's defaults.

    Used as the fallback when no preset is selected, and as the seed values for
    newly-saved presets so every parameter has an explicit value on disk.
    """
    return {
        "name": "Default",
        "description": "FilmFilter default values from the schema.",
        "pipeline": list(STAGE_ORDER),
        "effects": {name: stage_defaults(name) for name in STAGE_ORDER},
    }
