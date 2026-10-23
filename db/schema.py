"""Table definitions. Every statement is safe to run repeatedly."""

import logging

from db.database import Database

log = logging.getLogger("wisp")

_KEY_LINE_STARTS = ("PRIMARY", "UNIQUE", "INDEX", "KEY")

_DEFINITIONS: dict[str, str] = {
    "settings": """
        guild_id BIGINT NOT NULL,
        tracks_channel_id BIGINT NULL,
        house_channel_id BIGINT NULL,
        studio_forum_id BIGINT NULL,
        status_thread_id BIGINT NULL,
        status_message_id BIGINT NULL,
        mealtime_thread_id BIGINT NULL,
        vault_thread_id BIGINT NULL,
        vault_message_id BIGINT NULL,
        jam_thread_id BIGINT NULL,
        rules_thread_id BIGINT NULL,
        rules_message_id BIGINT NULL,
        viibr_meal_points INT NULL,
        suno_meal_points INT NULL,
        frozen BOOL NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id)
    """,
    "qualifying_roles": """
        guild_id BIGINT NOT NULL,
        role_id BIGINT NOT NULL,
        PRIMARY KEY (guild_id, role_id)
    """,
    "lives": """
        id BIGINT NOT NULL AUTO_INCREMENT,
        guild_id BIGINT NOT NULL,
        version INT NOT NULL,
        phase VARCHAR(10) NOT NULL,
        stage VARCHAR(10) NOT NULL,
        care DOUBLE NOT NULL,
        egg_food INT NOT NULL DEFAULT 0,
        growth INT NOT NULL DEFAULT 0,
        laid_at DATETIME NOT NULL,
        hatch_started_at DATETIME NULL,
        hatched_at DATETIME NULL,
        stage_started_at DATETIME NULL,
        ended_at DATETIME NULL,
        last_tick_at DATETIME NOT NULL,
        phase_seconds DOUBLE NOT NULL DEFAULT 0,
        high_happiness_since DATETIME NULL,
        warned VARCHAR(10) NULL,
        hatched_by BIGINT NULL,
        peak_stage VARCHAR(10) NOT NULL,
        from_coal BOOL NOT NULL DEFAULT 0,
        favorite_snack VARCHAR(20) NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uq_guild_version (guild_id, version)
    """,
    "players": """
        guild_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        activated_at DATETIME NULL,
        met_at DATETIME NULL,
        name VARCHAR(24) NULL,
        lifetime_points INT NOT NULL DEFAULT 0,
        balance INT NOT NULL DEFAULT 0,
        bond INT NOT NULL DEFAULT 0,
        pickle_stance VARCHAR(4) NULL,
        offenses INT NOT NULL DEFAULT 0,
        banned_until DATETIME NULL,
        banned_forever BOOL NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    """,
    "feeds": """
        id BIGINT NOT NULL AUTO_INCREMENT,
        guild_id BIGINT NOT NULL,
        life_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        track_key VARCHAR(80) NOT NULL,
        url VARCHAR(255) NOT NULL,
        meal_points INT NOT NULL,
        message_id BIGINT NOT NULL,
        fed_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uq_guild_track (guild_id, track_key)
    """,
    "interactions": """
        id BIGINT NOT NULL AUTO_INCREMENT,
        guild_id BIGINT NOT NULL,
        life_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        kind VARCHAR(8) NOT NULL,
        bond INT NOT NULL,
        meal_points INT NOT NULL,
        at DATETIME NOT NULL,
        PRIMARY KEY (id),
        INDEX idx_guild_user_at (guild_id, user_id, at)
    """,
    "inventory": """
        guild_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        snack VARCHAR(20) NOT NULL,
        qty INT NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, snack)
    """,
    "keepsakes": """
        guild_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        kind VARCHAR(20) NOT NULL,
        version INT NOT NULL,
        given_at DATETIME NOT NULL,
        PRIMARY KEY (guild_id, user_id, kind, version)
    """,
    "notes": """
        id BIGINT NOT NULL AUTO_INCREMENT,
        guild_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        note VARCHAR(200) NOT NULL,
        at DATETIME NOT NULL,
        PRIMARY KEY (id),
        INDEX idx_guild_user_at (guild_id, user_id, at)
    """,
    "favorites": """
        guild_id BIGINT NOT NULL,
        day DATE NOT NULL,
        user_id BIGINT NOT NULL,
        track_key VARCHAR(80) NOT NULL,
        url VARCHAR(255) NOT NULL,
        picked_at DATETIME NOT NULL,
        PRIMARY KEY (guild_id, day)
    """,
    "expression_uses": """
        guild_id BIGINT NOT NULL,
        name VARCHAR(40) NOT NULL,
        uses INT NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, name)
    """,
}

# Columns added after their table first went live, by table and column name.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "players": {"best_rhyme_score": "INT NOT NULL DEFAULT 0"},
}

TABLES: tuple[str, ...] = tuple(_DEFINITIONS)


class SchemaError(Exception):
    """A table in the database lacks columns the code needs."""


def _defined_columns(name: str) -> set[str]:
    """The column names of a table: the first word of each non-key line."""
    lines = (line.strip() for line in _DEFINITIONS[name].splitlines())
    columns = {
        line.split()[0]
        for line in lines
        if line and not line.upper().startswith(_KEY_LINE_STARTS)
    }
    return columns | set(_ADDED_COLUMNS.get(name, {}))


async def _columns(db: Database, name: str) -> set[str]:
    rows = await db.fetchall(
        "SELECT column_name AS name FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        (db.t(name),),
    )
    return {row["name"] for row in rows}


async def create_tables(db: Database) -> None:
    """Create every table that does not exist yet, then add any missing columns.

    Columns that are already there are skipped, so a normal startup does not
    draw a duplicate column note from the server. Afterwards every table is
    checked against its definition: extra columns are logged as a warning.

    Raises:
        SchemaError: A table lacks a defined column, so it was built from an
            older schema and must be rebuilt.
    """
    rows = await db.fetchall(
        "SELECT table_name AS name FROM information_schema.tables "
        "WHERE table_schema = DATABASE()"
    )
    existing = {row["name"] for row in rows}
    for name, columns in _DEFINITIONS.items():
        if db.t(name) not in existing:
            await db.execute(
                f"CREATE TABLE {db.t(name)} ({columns}) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )
    for name, added in _ADDED_COLUMNS.items():
        present = await _columns(db, name)
        for column, definition in added.items():
            if column not in present:
                await db.execute(
                    f"ALTER TABLE {db.t(name)} "
                    f"ADD COLUMN IF NOT EXISTS {column} {definition}"
                )
    await _check_columns(db)


async def _check_columns(db: Database) -> None:
    for name in _DEFINITIONS:
        defined = _defined_columns(name)
        present = await _columns(db, name)
        if missing := defined - present:
            raise SchemaError(
                f"Table {db.t(name)} is missing columns: {', '.join(sorted(missing))}"
            )
        if extra := present - defined:
            log.warning(
                "Table %s has columns Wisp does not use: %s",
                db.t(name),
                ", ".join(sorted(extra)),
            )
