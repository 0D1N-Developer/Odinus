"""Persistence and generic announcement services for Odinus."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord

if TYPE_CHECKING:
    from discord.ext.commands import Bot


LOGGER = logging.getLogger(__name__)

MEXICO_TIMEZONE = ZoneInfo("America/Mexico_City")


@dataclass(frozen=True)
class AnnouncementEvent:
    """Generic event that can be published by the announcement center."""

    platform: str
    external_id: str
    event_type: str
    title: str
    url: str | None = None
    description: str | None = None
    published_at: str | None = None
    author_name: str | None = None
    author_icon_url: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    platform_icon_url: str | None = None


@dataclass(frozen=True)
class AnnouncementConfig:
    """Configuration for one announcement source."""

    guild_id: int
    platform: str
    channel_id: int
    mention_role_id: int | None
    enabled: bool


class AnnouncementRepository:
    """Persistent data used by the announcement center."""

    def __init__(
        self,
        database_path: Path = Path("data") / "odinus.db",
    ) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        """Create announcement tables if needed."""
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS announcement_settings (
                    guild_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    channel_id INTEGER NOT NULL,
                    mention_role_id INTEGER,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (guild_id, platform)
                );

                CREATE TABLE IF NOT EXISTS announcement_events (
                    guild_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT,
                    published_at TEXT,
                    discord_message_id INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (
                        guild_id,
                        platform,
                        external_id
                    )
                );
                """
            )

    def configure(
        self,
        guild_id: int,
        platform: str,
        channel_id: int,
        mention_role_id: int | None,
    ) -> None:
        """Create or update a platform configuration."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO announcement_settings (
                    guild_id,
                    platform,
                    channel_id,
                    mention_role_id,
                    enabled
                )
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(guild_id, platform) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    mention_role_id = excluded.mention_role_id
                """,
                (
                    guild_id,
                    platform,
                    channel_id,
                    mention_role_id,
                ),
            )

    def get_config(
        self,
        guild_id: int,
        platform: str,
    ) -> AnnouncementConfig | None:
        """Return one platform configuration."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    guild_id,
                    platform,
                    channel_id,
                    mention_role_id,
                    enabled
                FROM announcement_settings
                WHERE guild_id = ? AND platform = ?
                """,
                (
                    guild_id,
                    platform,
                ),
            ).fetchone()

        if row is None:
            return None

        return AnnouncementConfig(
            guild_id=int(row[0]),
            platform=str(row[1]),
            channel_id=int(row[2]),
            mention_role_id=(
                int(row[3])
                if row[3] is not None
                else None
            ),
            enabled=bool(row[4]),
        )

    def get_configs(
        self,
        guild_id: int,
    ) -> list[AnnouncementConfig]:
        """Return all configured announcement sources."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    guild_id,
                    platform,
                    channel_id,
                    mention_role_id,
                    enabled
                FROM announcement_settings
                WHERE guild_id = ?
                ORDER BY platform
                """,
                (guild_id,),
            ).fetchall()

        return [
            AnnouncementConfig(
                guild_id=int(row[0]),
                platform=str(row[1]),
                channel_id=int(row[2]),
                mention_role_id=(
                    int(row[3])
                    if row[3] is not None
                    else None
                ),
                enabled=bool(row[4]),
            )
            for row in rows
        ]

    def set_enabled(
        self,
        guild_id: int,
        platform: str,
        enabled: bool,
    ) -> bool:
        """Enable or disable an announcement source."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE announcement_settings
                SET enabled = ?
                WHERE guild_id = ? AND platform = ?
                """,
                (
                    int(enabled),
                    guild_id,
                    platform,
                ),
            )

        return cursor.rowcount > 0

    def event_exists(
        self,
        guild_id: int,
        platform: str,
        external_id: str,
    ) -> bool:
        """Return whether an event has already been processed."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM announcement_events
                WHERE
                    guild_id = ?
                    AND platform = ?
                    AND external_id = ?
                LIMIT 1
                """,
                (
                    guild_id,
                    platform,
                    external_id,
                ),
            ).fetchone()

        return row is not None

    def has_events(
        self,
        guild_id: int,
        platform: str,
    ) -> bool:
        """Return whether a source already has event history."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM announcement_events
                WHERE guild_id = ? AND platform = ?
                LIMIT 1
                """,
                (
                    guild_id,
                    platform,
                ),
            ).fetchone()

        return row is not None

    def record_event(
        self,
        guild_id: int,
        platform: str,
        external_id: str,
        event_type: str,
        title: str,
        url: str | None,
        published_at: str | None,
        discord_message_id: int | None,
    ) -> None:
        """Record an announcement event."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO announcement_events (
                    guild_id,
                    platform,
                    external_id,
                    event_type,
                    title,
                    url,
                    published_at,
                    discord_message_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    platform,
                    external_id,
                    event_type,
                    title,
                    url,
                    published_at,
                    discord_message_id,
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)


class AnnouncementService:
    """Publish generic announcement events to Discord."""

    def __init__(
        self,
        bot: Bot,
        repository: AnnouncementRepository,
    ) -> None:
        self.bot = bot
        self.repository = repository

    async def publish_event(
        self,
        guild: discord.Guild,
        event: AnnouncementEvent,
    ) -> bool:
        """Publish an event using the guild configuration."""
        config = self.repository.get_config(
            guild.id,
            event.platform,
        )

        if config is None or not config.enabled:
            return False

        channel = guild.get_channel(config.channel_id)

        if not isinstance(channel, discord.TextChannel):
            LOGGER.warning(
                "Announcement channel %s not found or is not a text channel "
                "in guild %s.",
                config.channel_id,
                guild.id,
            )
            return False

        if self.repository.event_exists(
            guild.id,
            event.platform,
            event.external_id,
        ):
            return False

        return await self._publish_event(
            guild,
            channel,
            config,
            event,
        )

    async def publish_to_all_guilds(
        self,
        event: AnnouncementEvent,
    ) -> int:
        """Publish an event to every configured guild."""
        published = 0

        for guild in self.bot.guilds:
            if await self.publish_event(guild, event):
                published += 1

        return published

    async def _publish_event(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        config: AnnouncementConfig,
        event: AnnouncementEvent,
    ) -> bool:
        """Publish one event to one Discord channel."""
        author_name = event.author_name or "Odinus"

        platform_name = {
            "minecraft": "Minecraft",
            "blacktibii": "BlackTibii.com",
        }.get(
            event.platform,
            event.platform,
        )

        announcement_text = self._announcement_text(
            event,
            author_name,
            platform_name,
        )

        content_lines: list[str] = []

        if config.mention_role_id is not None:
            role = guild.get_role(config.mention_role_id)

            if role is not None:
                content_lines.append(
                    f"{role.mention} 💀 {announcement_text}"
                )
            else:
                content_lines.append(
                    f"@here 💀 {announcement_text}"
                )
        else:
            content_lines.append(
                f"@here 💀 {announcement_text}"
            )

        content_lines.append("")
        content_lines.append(event.title)

        if event.url:
            content_lines.extend(
                [
                    "",
                    f"🔗 [Ver más]({event.url})",
                ]
            )

        content = "\n".join(content_lines)

        embed = self._build_embed(
            event,
            author_name,
            platform_name,
        )

        allowed_mentions = discord.AllowedMentions(
            everyone=True,
            roles=True,
            users=False,
        )

        try:
            message = await channel.send(
                content=content,
                embed=embed,
                allowed_mentions=allowed_mentions,
            )

        except discord.Forbidden:
            LOGGER.error(
                "Missing permissions to publish announcement "
                "in guild %s, channel %s.",
                guild.id,
                channel.id,
            )
            return False

        except discord.HTTPException:
            LOGGER.exception(
                "Discord rejected announcement "
                "in guild %s, channel %s.",
                guild.id,
                channel.id,
            )
            return False

        self.repository.record_event(
            guild_id=guild.id,
            platform=event.platform,
            external_id=event.external_id,
            event_type=event.event_type,
            title=event.title,
            url=event.url,
            published_at=event.published_at,
            discord_message_id=message.id,
        )

        LOGGER.info(
            "Published %s announcement '%s' "
            "in guild %s, message %s.",
            platform_name,
            event.title,
            guild.id,
            message.id,
        )

        return True

    @staticmethod
    def _announcement_text(
        event: AnnouncementEvent,
        author_name: str,
        platform_name: str,
    ) -> str:
        """Build the generic announcement message."""
        event_type = event.event_type.lower()

        if event.platform == "minecraft":
            if event_type == "server_online":
                return "El servidor de Minecraft está en línea!"

            if event_type == "event":
                return "Hay un nuevo evento en Minecraft!"

            if event_type == "update":
                return "Hay una nueva actualización del servidor!"

            return f"{author_name} publicó una novedad de Minecraft!"

        if event.platform == "blacktibii":
            if event_type == "release":
                return "Black Tibii tiene un nuevo lanzamiento!"

            if event_type == "news":
                return "Black Tibii publicó una nueva noticia!"

            return "BlackTibii.com tiene una nueva actualización!"

        return f"{author_name} publicó una nueva actualización!"

    @staticmethod
    def _build_embed(
        event: AnnouncementEvent,
        author_name: str,
        platform_name: str,
    ) -> discord.Embed:
        """Build the standard announcement embed."""
        description = (
            event.description.strip()
            if event.description
            else "No hay descripción disponible."
        )

        embed = discord.Embed(
            title=event.title[:256],
            url=event.url,
            description=description[:4096],
            color=discord.Color.blurple(),
        )

        if event.author_name:
            embed.set_author(
                name=author_name[:256],
                icon_url=event.author_icon_url,
            )

        if event.image_url:
            embed.set_thumbnail(
                url=event.image_url,
            )

        if event.thumbnail_url:
            embed.set_image(
                url=event.thumbnail_url,
            )

        footer_text = platform_name

        if event.published_at:
            try:
                published_at = datetime.fromisoformat(
                    event.published_at.replace(
                        "Z",
                        "+00:00",
                    )
                )

                if published_at.tzinfo is not None:
                    published_at = published_at.astimezone(
                        MEXICO_TIMEZONE,
                    )

                hour = published_at.strftime("%I:%M %p")

                hour = (
                    hour.replace("AM", "a. m.")
                    .replace("PM", "p. m.")
                )

                footer_text = (
                    f"{platform_name} • "
                    f"{published_at.strftime('%d/%m/%Y')} "
                    f"{hour}"
                )

            except ValueError:
                LOGGER.warning(
                    "Invalid publication date for %s: %s",
                    platform_name,
                    event.published_at,
                )

        embed.set_footer(
            text=footer_text,
            icon_url=event.platform_icon_url,
        )

        return embed
