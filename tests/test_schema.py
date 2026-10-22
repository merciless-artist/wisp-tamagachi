import pymysql
import pytest

from db.database import Database
from db.schema import TABLES, create_tables


async def test_create_tables_is_idempotent(db: Database) -> None:
    await create_tables(db)
    rows = await db.fetchall("SHOW TABLES LIKE %s", (r"wisptest\_%",))
    assert len(rows) == len(TABLES)


async def test_create_tables_adds_columns_missing_from_older_tables(
    db: Database,
) -> None:
    players = db.t("players")
    await db.execute(f"ALTER TABLE {players} DROP COLUMN best_rhyme_score")

    await create_tables(db)

    columns = await db.fetchall(f"SHOW COLUMNS FROM {players}")
    assert "best_rhyme_score" in {column["Field"] for column in columns}
    await db.execute(f"INSERT INTO {players} (guild_id, user_id) VALUES (1, 1)")
    row = await db.fetchone(f"SELECT best_rhyme_score FROM {players}")
    assert row == {"best_rhyme_score": 0}


async def test_track_key_is_unique_per_guild(db: Database) -> None:
    insert = (
        f"INSERT INTO {db.t('feeds')} "
        "(guild_id, life_id, user_id, track_key, url, meal_points, message_id, "
        "fed_at) VALUES (1, 1, 1, 'suno:a', 'u', 1, 1, UTC_TIMESTAMP())"
    )
    await db.insert(insert)
    with pytest.raises(pymysql.err.IntegrityError):
        await db.insert(insert)
