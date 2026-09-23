"""Persistence and announcement services for Odinus."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord

from odinus.integrations.anuncios.base import AnnouncementEvent
from odinus.integrations.anuncios.youtube import YouTubeIntegration

if TYPE_CHECKING:
    from odinus.config import Settings


LOGGER = logging.getLogger(__name__)

MEXICO_TIMEZONE = ZoneInfo(
    "America/Mexico_City"
)


@dataclass(frozen=True)
class AnnouncementConfig:
    """Configuration for one announcement integration."""

    guild_id: int
    platform: str
    channel_id: int
    mention_role_id: int | None
    enabled: bool


class AnnouncementRepository:
    """Own persistent data used by the announcement center."""

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
        """Create or replace a platform configuration."""
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
        """Return a platform configuration."""
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
        """Return every configured integration for a guild."""
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
        """Enable or disable a configured integration."""
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
        """Return whether an external event was already processed."""
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
        """Return whether the guild already has event history."""
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
        """Record an announcement event as processed."""
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
    """Coordinate external integrations and Discord announcements."""

    def __init__(
        self,
        bot: discord.Client,
        settings: Settings,
        repository: AnnouncementRepository,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.repository = repository

        self.youtube = YouTubeIntegration(settings)

    async def poll_youtube(self) -> None:
        """Check YouTube and publish new events to configured guilds."""
        try:
            events = await self.youtube.fetch_events()

        except Exception:
            LOGGER.exception(
                "Unexpected error while polling YouTube."
            )
            return

        if not events:
            LOGGER.info(
                "YouTube polling completed: no events found."
            )
            return

        for guild in self.bot.guilds:
            config = self.repository.get_config(
                guild.id,
                "youtube",
            )

            if config is None or not config.enabled:
                continue

            await self._process_guild_events(
                guild,
                config,
                events,
            )

    async def _process_guild_events(
        self,
        guild: discord.Guild,
        config: AnnouncementConfig,
        events: list[AnnouncementEvent],
    ) -> None:
        """Process YouTube events for one configured guild."""
        channel = guild.get_channel(
            config.channel_id
        )

        if channel is None:
            LOGGER.warning(
                "Announcement channel %s not found in guild %s.",
                config.channel_id,
                guild.id,
            )
            return

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            LOGGER.warning(
                "Configured announcement channel %s in guild %s "
                "is not a text channel.",
                config.channel_id,
                guild.id,
            )
            return

        has_history = self.repository.has_events(
            guild.id,
            config.platform,
        )

        for event in reversed(events):
            if self.repository.event_exists(
                guild.id,
                event.platform,
                event.external_id,
            ):
                continue

            if not has_history:
                self.repository.record_event(
                    guild_id=guild.id,
                    platform=event.platform,
                    external_id=event.external_id,
                    event_type=event.event_type,
                    title=event.title,
                    url=event.url,
                    published_at=event.published_at,
                    discord_message_id=None,
                )

                continue

            await self._publish_event(
                guild,
                channel,
                config,
                event,
            )

    async def _publish_event(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        config: AnnouncementConfig,
        event: AnnouncementEvent,
    ) -> None:
        """Publish one external event to Discord."""
        author_name = (
            event.author_name
            or "Black Tibii"
        )

        content_lines: list[str] = []

        if config.mention_role_id is not None:
            role = guild.get_role(
                config.mention_role_id
            )

            if role is not None:
                content_lines.append(
                    f"{role.mention} 💀 "
                    f"{author_name} ha subido un nuevo video! 📹"
                )
            else:
                content_lines.append(
                    f"@here 💀 "
                    f"{author_name} ha subido un nuevo video! 📹"
                )
        else:
            content_lines.append(
                f"@here 💀 "
                f"{author_name} ha subido un nuevo video! 📹"
            )

        content_lines.extend(
            [
                "",
                event.title,
                "",
                f"🔗 [Ver en YouTube]({event.url})",
            ]
        )

        content = "\n".join(
            content_lines
        )

        embed = self._build_embed(
            event,
            author_name,
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
                "Missing permissions to publish YouTube "
                "announcement in guild %s, channel %s.",
                guild.id,
                channel.id,
            )
            return

        except discord.HTTPException:
            LOGGER.exception(
                "Discord rejected YouTube announcement "
                "in guild %s, channel %s.",
                guild.id,
                channel.id,
            )
            return

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
            "Published YouTube announcement '%s' "
            "in guild %s, message %s.",
            event.title,
            guild.id,
            message.id,
        )

    @staticmethod
    def _build_embed(
        event: AnnouncementEvent,
        author_name: str,
    ) -> discord.Embed:
        """Build the visual YouTube announcement embed."""
        embed = discord.Embed(
            title=event.title[:256],
            url=event.url,
            description=(
                f"{author_name} publicó un nuevo video "
                "en YouTube."
            ),
            color=discord.Color.red(),
        )

        embed.set_author(
            name=author_name[:256]
        )

        description = (
            event.description.strip()
            if event.description
            else "No description"
        )

        embed.add_field(
            name="Descripción",
            value=description[:4096],
            inline=False,
        )

        if event.thumbnail_url:
            embed.set_image(
                url=event.thumbnail_url
            )

        footer_text = "YouTube"

        if event.published_at:
            try:
                published_at = datetime.fromisoformat(
                    event.published_at.replace(
                        "Z",
                        "+00:00",
                    )
                )

                published_at = published_at.astimezone(
                    MEXICO_TIMEZONE
                )

                hour = published_at.strftime(
                    "%I:%M %p"
                )

                hour = (
                    hour.replace(
                        "AM",
                        "a. m.",
                    )
                    .replace(
                        "PM",
                        "p. m.",
                    )
                )

                footer_text = (
                    f"YouTube • "
                    f"{published_at.strftime('%d/%m/%Y')} "
                    f"{hour}"
                )

            except ValueError:
                LOGGER.warning(
                    "Invalid YouTube publication date: %s",
                    event.published_at,
                )

        embed.set_footer(
            text=footer_text
        )

        return embed