"""SQLite persistence for Invite Management channel settings."""

import sqlite3
from pathlib import Path


class InvitationRepository:
    """Own the local settings used by the invitation tracking feature."""

    def __init__(self, database_path: Path = Path("data") / "odinus.db") -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        """Create the invitation settings schema if needed."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS invitation_settings (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL
                )
                """
            )

    def set_channel(self, guild_id: int, channel_id: int) -> None:
        """Create or replace a server's invitation tracking channel."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO invitation_settings (guild_id, channel_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
                """,
                (guild_id, channel_id),
            )

    def channel_id_for_guild(self, guild_id: int) -> int | None:
        """Return the configured tracking channel for a server, if any."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT channel_id FROM invitation_settings WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
        return None if row is None else row[0]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)
