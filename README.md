# FilmFilter

FilmFilter is a small Python image-processing project for subtle, emotionally believable film-emulation looks. It is inspired by scanned print film, disposable cameras, 90s/2000s consumer portraits, toy digital cameras, soft highlight rolloff, restrained halation, and realistic grain.

The project is intentionally **not** a physically accurate film chemistry simulator, a LUT pack, a VHS/glitch tool, or an over-stylized social media filter. The goal is a soft photographic foundation that can grow carefully over time.

## Visual Philosophy

FilmFilter aims for images that feel:

- nostalgic
- soft
- photographic
- consumer-grade
- imperfect in believable ways

The default aesthetic favors:

- soft highlight compression instead of clipped digital whites
- lifted blacks instead of crushed shadows
- reduced microcontrast instead of brittle sharpness
- warm but restrained highlight color
- cross-channel color response instead of isolated RGB adjustment
- nonlinear saturation compression near tonal extremes
- muted olive greens
- subtle bloom and halation
- fine procedural grain
- gentle optical imperfections

FilmFilter avoids:

- giant fake grain
- heavy blur
- orange-and-teal grading
- fake dust overlays
- VHS artifacts
- extreme vignettes
- hardcoded preset values scattered across the codebase

## Architecture

The project is built around a JSON-driven, sequential pipeline. Images are loaded as RGB float arrays in the `0..1` range. Each module receives an image, applies one aesthetic transform, and returns a new image for the next stage.

Current stages:

1. `tone` — lifted blacks, softened contrast, and creamy luminance-based highlight shoulder while preserving midtones.
2. `color` — restrained saturation, tonal-region color crossover, muted greens, warm highlights, and a slight magenta skin bias.
3. `halation` — highlight isolation, Gaussian blur, warm tint, and subtle additive blending.
4. `sharpness` — optional edge-aware digital sharpness reduction, disabled by default.
5. `grain` — integrated media texture: layered grain, density variation, scanner-like softness, tiny spatial instability, and texture-aware color breakup.
6. `lens` — subtle vignette, edge softness, and optional tiny chromatic aberration.

Preset files live in `presets/`. The first preset is `soft_portrait_400.json`, which defines both the stage order and effect strengths.

## Project Structure

```text
FilmFilter/
├── presets/
│   └── soft_portrait_400.json
├── pipeline/
│   ├── tone.py
│   ├── color.py
│   ├── tonal.py
│   ├── halation.py
│   ├── sharpness.py
│   ├── grain.py
│   ├── lens.py
│   └── pipeline.py
├── input/
├── output/
├── tests/
├── cli.py
├── requirements.txt
├── README.md
└── AGENTS.md
```

## Installation

FilmFilter targets Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Place a source image anywhere on disk, then run:

```bash
python cli.py input.jpg --preset soft_portrait_400
```

By default, output is written to:

```text
output/input_soft_portrait_400.jpg
```

You can choose a custom destination:

```bash
python cli.py input.jpg --preset soft_portrait_400 --output output/example.jpg
```

## Presets

Presets are JSON files that define the ordered pipeline and per-stage parameters. Example:

```json
{
  "pipeline": ["tone", "color", "halation", "sharpness", "grain", "lens"],
  "effects": {
    "tone": {
      "enabled": true,
      "black_lift": 0.045,
      "contrast_softness": 0.18,
      "highlight_compression": 0.38,
      "shoulder_strength": 0.42
    }
  }
}
```

This keeps aesthetic choices centralized, inspectable, and easy to tune without editing implementation files.

### Tone and Highlight Controls

Highlight behavior is critical to film perception because digital clipping often fails abruptly while print-like images bend bright values into a smoother shoulder. FilmFilter shapes luminance rather than each RGB channel independently, which helps highlights stay warm and bright without turning gray, muddy, or HDR-like.

- `black_lift` raises the deepest shadows so blacks feel like scanned paper density rather than crushed digital black.
- `contrast_softness` gently reduces brittle global contrast while keeping midtones usable for faces and ordinary objects.
- `highlight_compression` controls how much bright luminance bends away from hard clipping.
- `shoulder_strength` controls how strongly the creamy upper highlight shoulder is blended into the result.
- `shadow_chroma_damping` reduces color casts that become more visible when deep blacks are lifted.

### Cross-Channel Color Controls

Film color should not feel like three independent RGB sliders. Real film stocks, print paper, and scanners all introduce small cross-channel interactions: reds compress before pure clipping, greens drift toward olive, blues lose purity in deep shadows, and highlights become creamier as saturation rolls off. FilmFilter models this as a restrained color stage driven by reusable shadow, midtone, and highlight masks from `pipeline/tonal.py`.

- `crossover_strength` controls subtle channel mixing, red highlight compression, olive foliage drift, and shadow blue compression.
- `saturation_compression` reduces color purity nonlinearly near shadows, highlights, and clipping pressure while protecting midtone richness.
- `highlight_desaturation` makes bright saturated colors pastelize instead of staying digitally pure near white.
- `shadow_color_shift` applies a very small cyan-leaning shadow bias, useful for scanned-print impurity without turning shadows teal.
- `highlight_warmth` remains the main control for creamy print-like highlight warmth.

These controls should stay conservative. The intended result is smoother color transitions, more organic overexposure behavior, and warmer emotional realism, not a visible LUT-heavy or orange-and-teal grade.

### Media Texture Controls

Real film grain is not a uniform transparent overlay. Scanned prints carry a hierarchy of fine silver/dye texture, mid-frequency paper or emulsion structure, and barely visible density variation. Those layers interact with exposure, local contrast, color purity, and scanner softness. FilmFilter keeps this behavior subtle so texture feels embedded in the photograph rather than pasted over it.

- `grain_amount` controls the overall texture strength; defaults should stay subtle.
- `grain_size` controls the scale of the blended procedural noise.
- `grain_shadow_bias` shifts texture visibility toward shadows and midtones.
- `grain_chromaticity` blends restrained color variation into mostly monochrome grain.
- `micro_grain_amount` controls fine texture that gives the image a scanned photographic surface.
- `mid_grain_amount` adds a quieter mid-frequency structure so grain does not read as a single digital noise scale.
- `density_variation_amount` adds extremely subtle low-frequency print density variation. Keep it very low to avoid cloudy or muddy output.
- `texture_scale_balance` shifts the texture hierarchy between crisp micro grain and broader organic structure.
- `scanner_softness`, `tonal_diffusion`, and `edge_softening` reduce excessive digital precision through restrained frequency-selective and edge-aware blending, not global blur.
- `chroma_instability`, `density_instability`, and `scan_irregularity` introduce barely perceptible color, density, and subpixel scan inconsistencies. These controls should remain near invisible.

Texture also participates in color rendering. Saturation and chroma are modulated slightly by the same procedural structure, with protection for likely skin tones and bright highlights. This softens RGB-clean transitions without creating a visible gimmick.

Subtle instability improves realism because photographic media and scanning are never perfectly uniform. Over-processing destroys that believability quickly: obvious warping, fake dust, giant grain, and strong color drift call attention to the effect instead of the photograph.

### Halation Controls

Halation should feel like a faint optical response around bright areas, not an obvious glow overlay. The `intensity_percent` control scales the existing halation recipe as a percentage, so presets can make the effect quieter without changing its threshold, radius, or warmth.

### Optional Sharpness Reduction

The `sharpness` stage is intentionally disabled by default through `soften_digital_sharpness: false`. When enabled, it uses mild edge-aware smoothing and selective microcontrast reduction to make oversharpened digital files feel less computational while preserving overall clarity.

- `soften_digital_sharpness` toggles the transform.
- `sharpness_softening_strength` controls the edge-aware softening amount.
- `microcontrast_reduction` controls how much small local contrast is attenuated.

## Current Limitations

FilmFilter is an early foundation. It currently has:

- no GUI
- no web app
- no GPU path
- no machine learning or deep learning
- no batch processing command yet
- no metadata preservation beyond basic image orientation handling
- no physically accurate film-stock modeling
- no automated perceptual quality tests

## Roadmap

Possible future additions:

- batch processing
- side-by-side contact sheet generation
- more presets with carefully documented intent
- preset schema validation
- stronger automated tests for stage ranges and determinism
- optional film border/crop tools that remain subtle
- better color-space management
- per-camera/lens imperfection profiles
- CLI controls for seed, output format, and batch directories

## Development Notes

The codebase prioritizes readability, documentation, and modularity over feature count. New effects should remain subtle by default and should explain their aesthetic purpose in docstrings.
