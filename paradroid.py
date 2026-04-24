#!/usr/bin/env python3
"""Entry point for bot-takeover-tui."""

from __future__ import annotations

import argparse
import sys

from bot_takeover_tui.app import run


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="bot-takeover-tui",
        description="Terminal Paradroid — Braybrook 1985 reimagined.",
    )
    ap.add_argument("--seed", type=int, default=0,
                    help="RNG seed (default 0)")
    args = ap.parse_args()
    run(seed=args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
