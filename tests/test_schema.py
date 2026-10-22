import pymysql
import pytest

from db.database import Database
from db.schema import TABLES, create_tables


async def test_create_tables_is_idempotent(db: Database) -> None:
    await create_tables(db)
    rows = await db.fetchall("SHOW TABLES LIKE %s", (r"wisptest\_%",))
    assert len(rows) == len(TABLES)


async def test_track_key_is_unique_per_guild(db: Database) -> None:
    insert = (
        f"INSERT INTO {db.t('feeds')} "
        "(guild_id, life_id, user_id, track_key, url, meal_points, message_id, "
        "fed_at) VALUES (1, 1, 1, 'suno:a', 'u', 1, 1, UTC_TIMESTAMP())"
    )
    await db.insert(insert)
    with pytest.raises(pymysql.err.IntegrityError):
        await db.insert(insert)
