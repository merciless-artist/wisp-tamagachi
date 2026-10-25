import logging

import pymysql
import pytest

from db.database import Database
from db.schema import TABLES, SchemaError, create_tables


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


async def test_create_tables_adds_the_faq_column_to_a_live_settings_table(
    db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    settings = db.t("settings")
    await db.execute(
        f"INSERT INTO {settings} (guild_id, house_channel_id) VALUES (1, 5)"
    )
    await db.execute(f"ALTER TABLE {settings} DROP COLUMN faq_message_ids")
    try:
        with caplog.at_level(logging.WARNING, logger="wisp"):
            await create_tables(db)

        columns = await db.fetchall(f"SHOW COLUMNS FROM {settings}")
        assert "faq_message_ids" in {column["Field"] for column in columns}
        row = await db.fetchone(
            f"SELECT house_channel_id, faq_message_ids FROM {settings}"
        )
        assert row == {"house_channel_id": 5, "faq_message_ids": None}
        assert caplog.records == []
    finally:
        restored = await db.fetchall(f"SHOW COLUMNS FROM {settings}")
        if "faq_message_ids" not in {column["Field"] for column in restored}:
            await db.execute(
                f"ALTER TABLE {settings} ADD COLUMN faq_message_ids TEXT NULL"
            )


async def test_create_tables_adds_removed_at_to_a_live_badges_table(
    db: Database,
) -> None:
    badges = db.t("badges")
    await db.execute(f"ALTER TABLE {badges} DROP COLUMN removed_at")
    try:
        await create_tables(db)

        columns = await db.fetchall(f"SHOW COLUMNS FROM {badges}")
        assert "removed_at" in {column["Field"] for column in columns}
    finally:
        restored = await db.fetchall(f"SHOW COLUMNS FROM {badges}")
        if "removed_at" not in {column["Field"] for column in restored}:
            await db.execute(
                f"ALTER TABLE {badges} ADD COLUMN removed_at DATETIME NULL"
            )


async def test_create_tables_adds_the_removal_index_to_a_live_badges_table(
    db: Database,
) -> None:
    badges = db.t("badges")
    await db.execute(f"DROP INDEX idx_guild_removed ON {badges}")

    await create_tables(db)

    rows = await db.fetchall(f"SHOW INDEX FROM {badges}")
    assert "idx_guild_removed" in {row["Key_name"] for row in rows}


async def test_create_tables_adds_lay_eggs_to_a_live_settings_table(
    db: Database,
) -> None:
    settings = db.t("settings")
    await db.execute(f"INSERT INTO {settings} (guild_id) VALUES (1)")
    await db.execute(f"ALTER TABLE {settings} DROP COLUMN lay_eggs")
    try:
        await create_tables(db)

        row = await db.fetchone(f"SELECT lay_eggs FROM {settings}")
        assert row == {"lay_eggs": 1}
    finally:
        restored = await db.fetchall(f"SHOW COLUMNS FROM {settings}")
        if "lay_eggs" not in {column["Field"] for column in restored}:
            await db.execute(
                f"ALTER TABLE {settings} ADD COLUMN lay_eggs BOOL NOT NULL DEFAULT 1"
            )


async def test_create_tables_adds_the_house_panel_to_a_live_settings_table(
    db: Database,
) -> None:
    settings = db.t("settings")
    await db.execute(f"INSERT INTO {settings} (guild_id) VALUES (1)")
    await db.execute(f"ALTER TABLE {settings} DROP COLUMN house_panel_message_id")
    try:
        await create_tables(db)

        row = await db.fetchone(f"SELECT house_panel_message_id FROM {settings}")
        assert row == {"house_panel_message_id": None}
    finally:
        restored = await db.fetchall(f"SHOW COLUMNS FROM {settings}")
        if "house_panel_message_id" not in {column["Field"] for column in restored}:
            await db.execute(
                f"ALTER TABLE {settings} ADD COLUMN house_panel_message_id BIGINT NULL"
            )


async def test_the_team_wisp_badge_becomes_team_viibr_and_renaming_repeats_safely(
    db: Database,
) -> None:
    roles = db.t("badge_roles")
    bought = db.t("badges")
    await db.execute(
        f"INSERT INTO {roles} (guild_id, badge, role_id) VALUES "
        "(1, 'team_wisp', 11), (1, 'flame_keeper', 12), "
        "(2, 'team_wisp', 21), (2, 'team_viibr', 22)"
    )
    await db.execute(
        f"INSERT INTO {bought} (guild_id, user_id, badge, life_id, version, "
        "bought_at) VALUES (1, 5, 'team_wisp', 3, 3, UTC_TIMESTAMP())"
    )

    for _ in range(2):
        await create_tables(db)

    rows = await db.fetchall(
        f"SELECT guild_id, badge, role_id FROM {roles} ORDER BY guild_id, role_id"
    )
    assert [(row["guild_id"], row["badge"], row["role_id"]) for row in rows] == [
        (1, "team_viibr", 11),
        (1, "flame_keeper", 12),
        (2, "team_wisp", 21),
        (2, "team_viibr", 22),
    ]
    assert await db.fetchall(f"SELECT badge FROM {bought}") == [{"badge": "team_viibr"}]


async def test_create_tables_adds_staff_roles_beside_live_tables(
    db: Database,
) -> None:
    settings = db.t("settings")
    staff_roles = db.t("staff_roles")
    await db.execute(f"INSERT INTO {settings} (guild_id) VALUES (1)")
    await db.execute(f"DROP TABLE {staff_roles}")

    await create_tables(db)

    assert await db.fetchone(f"SELECT guild_id FROM {settings}") == {"guild_id": 1}
    await db.execute(f"INSERT INTO {staff_roles} (guild_id, role_id) VALUES (1, 2)")
    with pytest.raises(pymysql.err.IntegrityError):
        await db.execute(f"INSERT INTO {staff_roles} (guild_id, role_id) VALUES (1, 2)")


async def test_track_key_is_unique_per_guild(db: Database) -> None:
    insert = (
        f"INSERT INTO {db.t('feeds')} "
        "(guild_id, life_id, user_id, track_key, url, meal_points, message_id, "
        "fed_at) VALUES (1, 1, 1, 'suno:a', 'u', 1, 1, UTC_TIMESTAMP())"
    )
    await db.insert(insert)
    with pytest.raises(pymysql.err.IntegrityError):
        await db.insert(insert)


async def test_matching_tables_pass_the_column_check(
    db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="wisp"):
        await create_tables(db)

    assert caplog.records == []


async def test_a_table_missing_a_column_refuses_to_start(db: Database) -> None:
    notes = db.t("notes")
    await db.execute(f"ALTER TABLE {notes} DROP COLUMN note")
    try:
        with pytest.raises(SchemaError, match=rf"{notes}.*\bnote\b"):
            await create_tables(db)
    finally:
        await db.execute(f"DROP TABLE {notes}")
        await create_tables(db)

    columns = await db.fetchall(f"SHOW COLUMNS FROM {notes}")
    assert "note" in {column["Field"] for column in columns}


async def test_an_extra_column_is_only_a_warning(
    db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    notes = db.t("notes")
    await db.execute(f"ALTER TABLE {notes} ADD COLUMN leftover INT NULL")
    try:
        with caplog.at_level(logging.WARNING, logger="wisp"):
            await create_tables(db)
    finally:
        await db.execute(f"ALTER TABLE {notes} DROP COLUMN leftover")

    assert any(
        record.levelno == logging.WARNING
        and notes in record.getMessage()
        and "leftover" in record.getMessage()
        for record in caplog.records
    )
