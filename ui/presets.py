"""Preset discovery, loading, and saving helpers for the UI layer.

The on-disk preset format is unchanged — these helpers wrap ``pipeline.pipeline``
so the editor can list, normalize, and save preset JSONs without duplicating
logic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pipeline.pipeline import PRESET_DIR, load_preset

from .schema import STAGE_BY_NAME, STAGE_ORDER, default_preset, stage_defaults


def list_preset_files() -> list[Path]:
    """Return preset JSON paths sorted by display name."""
    if not PRESET_DIR.exists():
        return []
    return sorted(PRESET_DIR.glob("*.json"), key=lambda p: p.stem.lower())


def load_preset_normalized(preset_path: Path) -> dict[str, Any]:
    """Load a preset from disk and fill in any missing parameter defaults.

    Older presets may not carry every parameter the current schema defines; this
    fills in the gaps so the UI always has a complete value set to render.
    """
    raw = load_preset(preset_path)
    return merge_with_schema_defaults(raw)


def merge_with_schema_defaults(preset: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``preset`` with all schema-known defaults filled in."""
    base = default_preset()
    merged: dict[str, Any] = {
        "name": preset.get("name", base["name"]),
        "description": preset.get("description", ""),
        "pipeline": list(preset.get("pipeline") or base["pipeline"]),
        "effects": {},
    }
    raw_effects = preset.get("effects", {}) or {}
    for stage_name in STAGE_ORDER:
        block = dict(stage_defaults(stage_name))
        block.update(raw_effects.get(stage_name, {}) or {})
        merged["effects"][stage_name] = block
    # Preserve any non-schema stage data that may exist (forward-compatibility).
    for stage_name, block in raw_effects.items():
        if stage_name not in STAGE_BY_NAME:
            merged["effects"][stage_name] = dict(block)
    return merged


def save_preset(preset_path: Path, preset: dict[str, Any]) -> None:
    """Write a preset to disk as pretty JSON."""
    preset_path.parent.mkdir(parents=True, exist_ok=True)
    with preset_path.open("w", encoding="utf-8") as handle:
        json.dump(preset, handle, indent=2)
        handle.write("\n")


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Convert a display name to a filesystem-safe preset stem."""
    slug = _SLUG_RE.sub("_", name.strip().lower()).strip("_")
    return slug or "untitled"


def unique_preset_path(stem: str) -> Path:
    """Return a preset path that does not collide with an existing file."""
    candidate = PRESET_DIR / f"{stem}.json"
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = PRESET_DIR / f"{stem}_{counter}.json"
        if not candidate.exists():
            return candidate
        counter += 1
