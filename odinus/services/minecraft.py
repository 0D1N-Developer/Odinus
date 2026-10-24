"""SQLite persistence for the Minecraft integration."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


CHANNEL_COLUMNS = {
    "chat": "chat_channel_id",
    "consola": "console_channel_id",
    "estado": "status_channel_id",
    "economia": "economy_channel_id",
    "vinculacion": "link_channel_id",
}

SETTINGS_COLUMNS = (
    "guild_id, chat_channel_id, console_channel_id, status_channel_id, "
    "status_message_id, economy_channel_id, link_channel_id, "
    "java_address, bedrock_address"
)

# Columnas añadidas después de la primera versión de la tabla.
ADDED_SETTINGS_COLUMNS = (
    ("link_channel_id", "INTEGER"),
    ("java_address", "TEXT"),
    ("bedrock_address", "TEXT"),
)


@dataclass(frozen=True)
class MinecraftLink:
    """A Discord account linked to a Minecraft player."""

    discord_id: int
    uuid: str
    name: str
    linked_at: str


@dataclass(frozen=True)
class MinecraftGuildSettings:
    """Channels used by the Minecraft integration in one server."""

    guild_id: int
    chat_channel_id: int | None = None
    console_channel_id: int | None = None
    status_channel_id: int | None = None
    status_message_id: int | None = None
    economy_channel_id: int | None = None
    link_channel_id: int | None = None
    java_address: str | None = None
    bedrock_address: str | None = None


class MinecraftRepository:
    """Store account links and per-server channel configuration.

    Links are global because Odinus is connected to a single Minecraft
    server; the bot is the source of truth for them, not the plugin.
    """

    def __init__(self, database_path: Path = Path("data") / "odinus.db") -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        """Create the Minecraft tables if they do not exist."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS minecraft_links (
                    discord_id INTEGER PRIMARY KEY,
                    uuid TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    linked_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS minecraft_settings (
                    guild_id INTEGER PRIMARY KEY,
                    chat_channel_id INTEGER,
                    console_channel_id INTEGER,
                    status_channel_id INTEGER,
                    status_message_id INTEGER,
                    economy_channel_id INTEGER
                )
                """
            )

            existing = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(minecraft_settings)"
                )
            }

            for column, column_type in ADDED_SETTINGS_COLUMNS:
                if column not in existing:
                    connection.execute(
                        f"ALTER TABLE minecraft_settings "
                        f"ADD COLUMN {column} {column_type}"
                    )

    # ---------------------------------------------------------------- links

    def link_for_discord(self, discord_id: int) -> MinecraftLink | None:
        """Return the link of a Discord user."""
        return self._fetch_link("discord_id = ?", discord_id)

    def link_for_uuid(self, player_uuid: str) -> MinecraftLink | None:
        """Return the link of a Minecraft player."""
        return self._fetch_link("uuid = ?", player_uuid)

    def save_link(
        self,
        discord_id: int,
        player_uuid: str,
        name: str,
    ) -> None:
        """Link a Discord user with a player, replacing older links.

        A player and a Discord user can only have one link each, so any
        previous link of either side is removed first.
        """
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM minecraft_links WHERE discord_id = ? OR uuid = ?",
                (discord_id, player_uuid),
            )
            connection.execute(
                """
                INSERT INTO minecraft_links (discord_id, uuid, name, linked_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    discord_id,
                    player_uuid,
                    name,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def delete_link_for_discord(self, discord_id: int) -> MinecraftLink | None:
        """Remove and return the link of a Discord user."""
        link = self.link_for_discord(discord_id)

        if link is not None:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM minecraft_links WHERE discord_id = ?",
                    (discord_id,),
                )

        return link

    def delete_link_for_uuid(self, player_uuid: str) -> MinecraftLink | None:
        """Remove and return the link of a Minecraft player."""
        link = self.link_for_uuid(player_uuid)

        if link is not None:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM minecraft_links WHERE uuid = ?",
                    (player_uuid,),
                )

        return link

    # ------------------------------------------------------------- settings

    def settings_for_guild(self, guild_id: int) -> MinecraftGuildSettings:
        """Return the channel configuration of a server."""
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {SETTINGS_COLUMNS} FROM minecraft_settings "
                "WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()

        if row is None:
            return MinecraftGuildSettings(guild_id)

        return MinecraftGuildSettings(*row)

    def all_settings(self) -> list[MinecraftGuildSettings]:
        """Return the configuration of every server."""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {SETTINGS_COLUMNS} FROM minecraft_settings"
            ).fetchall()

        return [MinecraftGuildSettings(*row) for row in rows]

    def set_channel(
        self,
        guild_id: int,
        kind: str,
        channel_id: int | None,
    ) -> None:
        """Set one of the integration channels (see ``CHANNEL_COLUMNS``)."""
        column = CHANNEL_COLUMNS[kind]

        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO minecraft_settings (guild_id) VALUES (?)",
                (guild_id,),
            )
            connection.execute(
                f"UPDATE minecraft_settings SET {column} = ? WHERE guild_id = ?",
                (channel_id, guild_id),
            )

    def set_status_message(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
    ) -> None:
        """Remember the status message that Odinus keeps editing."""
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO minecraft_settings (guild_id) VALUES (?)",
                (guild_id,),
            )
            connection.execute(
                """
                UPDATE minecraft_settings
                SET status_channel_id = ?, status_message_id = ?
                WHERE guild_id = ?
                """,
                (channel_id, message_id, guild_id),
            )

    def set_addresses(
        self,
        guild_id: int,
        java_address: str | None,
        bedrock_address: str | None,
    ) -> None:
        """Set the addresses players use to join the server."""
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO minecraft_settings (guild_id) VALUES (?)",
                (guild_id,),
            )
            connection.execute(
                """
                UPDATE minecraft_settings
                SET java_address = ?, bedrock_address = ?
                WHERE guild_id = ?
                """,
                (java_address, bedrock_address, guild_id),
            )

    def _fetch_link(self, condition: str, value: object) -> MinecraftLink | None:
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT discord_id, uuid, name, linked_at
                FROM minecraft_links
                WHERE {condition}
                """,
                (value,),
            ).fetchone()

        return MinecraftLink(*row) if row else None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)
