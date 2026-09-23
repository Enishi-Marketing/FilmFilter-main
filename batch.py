"""Batch-process all images in an input folder through the FilmFilter pipeline."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from pipeline.pipeline import FilmPipeline, read_image, write_image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".heic", ".heif",
                    ".arw", ".cr2", ".cr3", ".nef", ".nrw", ".raf", ".dng", ".rw2", ".orf", ".pef"}


def _fmt_time(seconds: float) -> str:
    """Format a duration as '1m 32s' or '45s'."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60:02d}s"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply film-emulation processing to every image in a folder.",
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        default="input",
        help="Folder containing source images (default: input/).",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="output",
        help="Destination folder for processed images (default: output/).",
    )
    parser.add_argument(
        "--preset",
        default="kodak_prima_400",
        help="Preset name from presets/ or path to a JSON preset.",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=95,
        help="JPEG quality for saved output files.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.is_dir():
        raise SystemExit(f"Error: '{input_dir}' is not a directory.")

    images = [p for p in sorted(input_dir.iterdir()) if p.suffix.lower() in IMAGE_EXTENSIONS]
    if not images:
        raise SystemExit(f"No supported images found in '{input_dir}'.")

    output_dir.mkdir(parents=True, exist_ok=True)
    preset_label = Path(args.preset).stem
    pipeline = FilmPipeline.from_preset_name(args.preset)

    total_start = time.monotonic()
    elapsed_per_image: list[float] = []

    for i, src in enumerate(images, 1):
        dest = output_dir / f"{src.stem}_{preset_label}.jpg"
        prefix = f"[{i}/{len(images)}] {src.name}"

        t0 = time.monotonic()

        print(f"{prefix}  loading …   ", end="\r", flush=True)
        image = read_image(src)

        print(f"{prefix}  processing …", end="\r", flush=True)
        processed = pipeline.process(image)

        print(f"{prefix}  saving …    ", end="\r", flush=True)
        write_image(dest, processed, quality=args.quality)

        elapsed = time.monotonic() - t0
        elapsed_per_image.append(elapsed)

        avg = sum(elapsed_per_image) / len(elapsed_per_image)
        remaining = (len(images) - i) * avg
        eta = f"  ETA {_fmt_time(remaining)}" if i < len(images) else ""
        print(f"{prefix}  → {dest.name}  ({elapsed:.1f}s){eta}    ")

    total = time.monotonic() - total_start
    print(f"\nDone — {len(images)} image(s) in {_fmt_time(total)}  written to '{output_dir}'.")


if __name__ == "__main__":
    main()
