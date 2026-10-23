"""Where Wisp's artwork lives on disk."""

from pathlib import Path
from typing import Final

ASSETS_DIR: Final = Path(__file__).resolve().parent.parent / "ASSETS"
