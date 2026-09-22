"""SQLite persistence for the age self-role configuration."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class AgeRepository:
    """Manage the configured age-role channel for each Discord server."""

    def __init__(self, database_path: Path = Path("data") / "odinus.db") -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        """Create the age settings table if it does not exist."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS age_settings (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL
                )
                """
            )

    def set_channel(self, guild_id: int, channel_id: int) -> None:
        """Set or replace the age self-role channel."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO age_settings (guild_id, channel_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id
                """,
                (guild_id, channel_id),
            )

    def channel_id_for_guild(self, guild_id: int) -> int | None:
        """Return the configured age channel."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT channel_id
                FROM age_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        return row[0] if row else None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)