"""Environment configuration, loaded from ``.env`` at import time."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TOKEN: str = os.environ["DISCORD_BOT_TOKEN"]

MYSQL: dict[str, str | int] = {
    "host": os.environ["MYSQL_HOST"],
    "port": int(os.environ["MYSQL_PORT"]),
    "user": os.environ["MYSQL_USER"],
    "password": os.environ["MYSQL_PASSWORD"],
    "db": os.environ["MYSQL_DATABASE"],
}

TABLE_PREFIX: str = os.environ.get("WISP_TABLE_PREFIX", "wisp_")


def _optional(name: str) -> str | None:
    """Return an environment setting, or None if it is unset or empty."""
    return os.environ.get(name) or None


GOOGLE_API_KEY: str | None = _optional("GOOGLE_API_KEY")
GOOGLE_CHAT_MODEL: str | None = _optional("GOOGLE_CHAT_MODEL")
GOOGLE_FALLBACK_MODEL: str | None = _optional("GOOGLE_FALLBACK_MODEL")
GOOGLE_VISION_MODEL: str = _optional("GOOGLE_VISION_MODEL") or "gemini-3.6-flash"
GOOGLE_EMBEDDING_MODEL: str = (
    _optional("GOOGLE_EMBEDDING_MODEL") or "gemini-embedding-2"
)
GROQ_API_KEY: str | None = _optional("GROQ_API_KEY")
GROQ_MODEL: str | None = _optional("GROQ_MODEL")
OPENROUTER_API_KEY: str | None = _optional("OPENROUTER_API_KEY")
OPENROUTER_MODEL: str | None = _optional("OPENROUTER_MODEL")
CF_IMAGE_WORKER_URL: str | None = _optional("CF_IMAGE_WORKER_URL")
MEMORY_PATH: str = _optional("WISP_MEMORY_PATH") or str(
    Path(__file__).parent / "data" / "memory"
)
