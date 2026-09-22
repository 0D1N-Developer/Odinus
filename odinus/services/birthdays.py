"""SQLite persistence for server birthday registrations and announcements."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Birthday:
    """A member birthday registered for a Discord server."""

    user_id: int
    day: int
    month: int
    year: int


class BirthdayRepository:
    """Own the local SQLite database used by the birthday feature."""

    def __init__(self, database_path: Path = Path("data") / "odinus.db") -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        """Create the schema if this is the first application start."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS birthdays (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    day INTEGER NOT NULL,
                    month INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS birthday_settings (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL
                );
                """
            )

    def save_birthday(
        self, guild_id: int, user_id: int, day: int, month: int, year: int
    ) -> None:
        """Create or replace the requesting member's birthday in one server."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO birthdays (guild_id, user_id, day, month, year)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    day = excluded.day,
                    month = excluded.month,
                    year = excluded.year
                """,
                (guild_id, user_id, day, month, year),
            )

    def set_announcement_channel(self, guild_id: int, channel_id: int) -> None:
        """Create or replace the configured announcement channel for a server."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO birthday_settings (guild_id, channel_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
                """,
                (guild_id, channel_id),
            )

    def configured_channels(self) -> list[tuple[int, int]]:
        """Return each server and its configured birthday announcement channel."""
        with self._connect() as connection:
            return connection.execute(
                "SELECT guild_id, channel_id FROM birthday_settings"
            ).fetchall()

    def birthdays_for_date(self, guild_id: int, day: int, month: int) -> list[Birthday]:
        """Find member birthdays matching a calendar day in a server."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT user_id, day, month, year
                FROM birthdays
                WHERE guild_id = ? AND day = ? AND month = ?
                """,
                (guild_id, day, month),
            ).fetchall()
        return [Birthday(*row) for row in rows]

    def birthdays_in_guild(self, guild_id: int) -> list[Birthday]:
        """Return all birthdays registered for one Discord server."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT user_id, day, month, year
                FROM birthdays
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchall()
        return [Birthday(*row) for row in rows]

    def leap_day_birthdays(self, guild_id: int) -> list[Birthday]:
        """Find February 29 birthdays for non-leap-year February 28 notices."""
        return self.birthdays_for_date(guild_id, day=29, month=2)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)
