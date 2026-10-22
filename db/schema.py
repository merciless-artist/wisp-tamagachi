"""Table definitions. Every statement is safe to run repeatedly."""

from db.database import Database

_DEFINITIONS: dict[str, str] = {
    "settings": """
        guild_id BIGINT NOT NULL,
        tracks_channel_id BIGINT NULL,
        house_channel_id BIGINT NULL,
        studio_forum_id BIGINT NULL,
        error_channel_id BIGINT NULL,
        status_thread_id BIGINT NULL,
        status_message_id BIGINT NULL,
        mealtime_thread_id BIGINT NULL,
        lunchbox_thread_id BIGINT NULL,
        jam_thread_id BIGINT NULL,
        billboard_thread_id BIGINT NULL,
        billboard_message_id BIGINT NULL,
        rules_thread_id BIGINT NULL,
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
}

# Columns added after their table first went live, by table and column name.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "players": {"best_rhyme_score": "INT NOT NULL DEFAULT 0"},
}

TABLES: tuple[str, ...] = tuple(_DEFINITIONS)


async def create_tables(db: Database) -> None:
    """Create every table that does not exist yet, then add any missing columns.

    Columns that are already there are skipped, so a normal startup does not
    draw a duplicate column note from the server.
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
        present = {
            row["name"]
            for row in await db.fetchall(
                "SELECT column_name AS name FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s",
                (db.t(name),),
            )
        }
        for column, definition in added.items():
            if column not in present:
                await db.execute(
                    f"ALTER TABLE {db.t(name)} "
                    f"ADD COLUMN IF NOT EXISTS {column} {definition}"
                )
