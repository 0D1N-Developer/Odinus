"""SQLite persistence for invitation tracking."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class InvitationRepository:
    """Own the persistent data used by invitation tracking."""

    def __init__(
        self,
        database_path: Path = Path("data") / "odinus.db",
    ) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        """Create invitation tracking tables if needed."""
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS invitation_settings (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS invitation_stats (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    total_invites INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS invitation_records (
                    guild_id INTEGER NOT NULL,
                    invite_code TEXT NOT NULL,
                    inviter_id INTEGER,
                    uses INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, invite_code)
                );
                """
            )

    def set_channel(
        self,
        guild_id: int,
        channel_id: int,
    ) -> None:
        """Create or replace a server's invitation tracking channel."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO invitation_settings (
                    guild_id,
                    channel_id
                )
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id
                """,
                (
                    guild_id,
                    channel_id,
                ),
            )

    def channel_id_for_guild(
        self,
        guild_id: int,
    ) -> int | None:
        """Return the configured tracking channel."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT channel_id
                FROM invitation_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        return None if row is None else int(row[0])

    def increment_user_invites(
        self,
        guild_id: int,
        user_id: int,
        amount: int = 1,
    ) -> int:
        """Increment and return a user's official invitation count."""
        amount = max(0, amount)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO invitation_stats (
                    guild_id,
                    user_id,
                    total_invites
                )
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    total_invites =
                        invitation_stats.total_invites
                        + excluded.total_invites
                """,
                (
                    guild_id,
                    user_id,
                    amount,
                ),
            )

            row = connection.execute(
                """
                SELECT total_invites
                FROM invitation_stats
                WHERE guild_id = ? AND user_id = ?
                """,
                (
                    guild_id,
                    user_id,
                ),
            ).fetchone()

        return int(row[0]) if row else 0

    def user_invites(
        self,
        guild_id: int,
        user_id: int,
    ) -> int:
        """Return the official invitation count for a user."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT total_invites
                FROM invitation_stats
                WHERE guild_id = ? AND user_id = ?
                """,
                (
                    guild_id,
                    user_id,
                ),
            ).fetchone()

        return int(row[0]) if row else 0

    def record_invite(
        self,
        guild_id: int,
        invite_code: str,
        inviter_id: int | None,
        uses: int,
    ) -> None:
        """Store the latest known usage of an invitation."""
        uses = max(0, uses)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO invitation_records (
                    guild_id,
                    invite_code,
                    inviter_id,
                    uses
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, invite_code) DO UPDATE SET
                    inviter_id = excluded.inviter_id,
                    uses = excluded.uses
                """,
                (
                    guild_id,
                    invite_code,
                    inviter_id,
                    uses,
                ),
            )

    def invitation_record(
        self,
        guild_id: int,
        invite_code: str,
    ) -> tuple[int | None, int] | None:
        """Return the last known inviter and usage for an invitation."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT inviter_id, uses
                FROM invitation_records
                WHERE guild_id = ? AND invite_code = ?
                """,
                (
                    guild_id,
                    invite_code,
                ),
            ).fetchone()

        if row is None:
            return None

        inviter_id = (
            int(row[0])
            if row[0] is not None
            else None
        )

        return inviter_id, int(row[1])

    def sync_invite_usage(
        self,
        guild_id: int,
        invite_code: str,
        inviter_id: int | None,
        current_uses: int,
    ) -> int:
        """
        Synchronize an invitation's current usage.

        Returns the number of new uses that were discovered.
        Existing historical uses are not counted twice.
        """
        current_uses = max(0, current_uses)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT inviter_id, uses
                FROM invitation_records
                WHERE guild_id = ? AND invite_code = ?
                """,
                (
                    guild_id,
                    invite_code,
                ),
            ).fetchone()

            if row is None:
                previous_uses = 0
                previous_inviter_id = None
            else:
                previous_inviter_id = (
                    int(row[0])
                    if row[0] is not None
                    else None
                )
                previous_uses = int(row[1])

            effective_inviter_id = (
                inviter_id
                if inviter_id is not None
                else previous_inviter_id
            )

            new_uses = max(
                0,
                current_uses - previous_uses,
            )

            if new_uses > 0 and effective_inviter_id is not None:
                connection.execute(
                    """
                    INSERT INTO invitation_stats (
                        guild_id,
                        user_id,
                        total_invites
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        total_invites =
                            invitation_stats.total_invites
                            + excluded.total_invites
                    """,
                    (
                        guild_id,
                        effective_inviter_id,
                        new_uses,
                    ),
                )

            connection.execute(
                """
                INSERT INTO invitation_records (
                    guild_id,
                    invite_code,
                    inviter_id,
                    uses
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, invite_code) DO UPDATE SET
                    inviter_id = excluded.inviter_id,
                    uses = excluded.uses
                """,
                (
                    guild_id,
                    invite_code,
                    effective_inviter_id,
                    current_uses,
                ),
            )

        return new_uses

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)