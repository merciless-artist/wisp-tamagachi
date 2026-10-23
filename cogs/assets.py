"""Wisp's artwork: where it lives on disk and the app emoji names shared by cogs."""

from pathlib import Path
from typing import Final

ASSETS_DIR: Final = Path(__file__).resolve().parent.parent / "ASSETS"
COIN_EMOJI: Final = "wisp_coin"
