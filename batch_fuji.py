"""Batch-process images using the Fuji Apple preset."""

from __future__ import annotations

import sys
import batch

_orig = batch.build_parser


def _build_parser_fuji():
    p = _orig()
    p.set_defaults(preset="fuji_apple")
    return p


batch.build_parser = _build_parser_fuji

if __name__ == "__main__":
    batch.main()
