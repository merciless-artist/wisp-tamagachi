"""Environment configuration, loaded from ``.env`` at import time."""

import os

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
