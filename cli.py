"""Command-line entry point for FilmFilter."""

from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.pipeline import FilmPipeline, read_image, write_image


def build_parser() -> argparse.ArgumentParser:
    """Build the first-pass CLI parser."""
    parser = argparse.ArgumentParser(
        description="Apply subtle film-emulation processing to an image.",
    )
    parser.add_argument("input", help="Path to the source image.")
    parser.add_argument(
        "--preset",
        default="soft_portrait_400",
        help="Preset name from presets/ or path to a JSON preset.",
    )
    parser.add_argument(
        "--output",
        help="Output path. Defaults to output/<input-stem>_<preset>.jpg.",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=95,
        help="JPEG quality for saved output files.",
    )
    return parser


def default_output_path(input_path: Path, preset: str) -> Path:
    """Return a predictable output path for CLI runs."""
    preset_label = Path(preset).stem
    return Path("output") / f"{input_path.stem}_{preset_label}.jpg"


def main() -> None:
    """Run the CLI image processing workflow."""
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else default_output_path(input_path, args.preset)

    pipeline = FilmPipeline.from_preset_name(args.preset)
    image = read_image(input_path)
    processed = pipeline.process(image)
    write_image(output_path, processed, quality=args.quality)

    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
