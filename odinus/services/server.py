"""Server information and persistent server-card services for Odinus."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import discord


LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = 60


DEFAULT_SETTINGS = {
    "name": None,
    "description": "Información actual de este servidor.",
    "website": None,
    "color": "#2B2D31",
    "thumbnail_url": None,
    "image_url": None,
    "show_online": True,
    "show_bots": True,
    "show_boosts": True,
    "show_channels": True,
    "show_roles": True,
    "show_emojis": True,
    "show_stickers": True,
    "show_owner": True,
    "show_created": True,
}


@dataclass(frozen=True)
class ServerCardConfig:
    """Persistent configuration for one server information card."""

    guild_id: int
    channel_id: int
    message_id: int
    enabled: bool


class ServerRepository:
    """Persist server information card configurations."""

    def __init__(
        self,
        database_path: Path = Path("data") / "odinus.db",
    ) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        """Create the server card tables if they do not exist."""
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS server_cards (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1
                );
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS server_card_settings (
                    guild_id INTEGER PRIMARY KEY,
                    settings TEXT NOT NULL
                );
                """
            )

    def configure(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
    ) -> None:
        """Create or replace the server card configuration."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO server_cards (
                    guild_id,
                    channel_id,
                    message_id,
                    enabled
                )
                VALUES (?, ?, ?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = excluded.message_id,
                    enabled = 1
                """,
                (
                    guild_id,
                    channel_id,
                    message_id,
                ),
            )

    def get_config(
        self,
        guild_id: int,
    ) -> ServerCardConfig | None:
        """Return the configured server card."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    guild_id,
                    channel_id,
                    message_id,
                    enabled
                FROM server_cards
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        if row is None:
            return None

        return ServerCardConfig(
            guild_id=int(row[0]),
            channel_id=int(row[1]),
            message_id=int(row[2]),
            enabled=bool(row[3]),
        )

    def get_enabled_configs(self) -> list[ServerCardConfig]:
        """Return all enabled server card configurations."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    guild_id,
                    channel_id,
                    message_id,
                    enabled
                FROM server_cards
                WHERE enabled = 1
                ORDER BY guild_id
                """
            ).fetchall()

        return [
            ServerCardConfig(
                guild_id=int(row[0]),
                channel_id=int(row[1]),
                message_id=int(row[2]),
                enabled=bool(row[3]),
            )
            for row in rows
        ]

    def set_enabled(
        self,
        guild_id: int,
        enabled: bool,
    ) -> bool:
        """Enable or disable the server card."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE server_cards
                SET enabled = ?
                WHERE guild_id = ?
                """,
                (
                    int(enabled),
                    guild_id,
                ),
            )

        return cursor.rowcount > 0

    def get_settings(
        self,
        guild_id: int,
    ) -> dict:
        """Return customized server card settings."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT settings
                FROM server_card_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        settings = dict(DEFAULT_SETTINGS)

        if row is None:
            return settings

        try:
            stored = json.loads(row[0])

            if isinstance(stored, dict):
                settings.update(stored)

        except (json.JSONDecodeError, TypeError):
            LOGGER.warning(
                "Invalid server card settings for guild %s.",
                guild_id,
            )

        return settings

    def save_settings(
        self,
        guild_id: int,
        settings: dict,
    ) -> None:
        """Persist customized server card settings."""
        clean_settings = dict(DEFAULT_SETTINGS)
        clean_settings.update(settings)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO server_card_settings (
                    guild_id,
                    settings
                )
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    settings = excluded.settings
                """,
                (
                    guild_id,
                    json.dumps(
                        clean_settings,
                        ensure_ascii=False,
                    ),
                ),
            )

    def reset_settings(
        self,
        guild_id: int,
    ) -> None:
        """Restore default server card settings."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO server_card_settings (
                    guild_id,
                    settings
                )
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    settings = excluded.settings
                """,
                (
                    guild_id,
                    json.dumps(
                        DEFAULT_SETTINGS,
                        ensure_ascii=False,
                    ),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)


class ServerService:
    """Provide server information and maintain permanent server cards."""

    def __init__(
        self,
        bot: discord.Client,
        repository: ServerRepository,
    ) -> None:
        self.bot = bot
        self.repository = repository
        self._update_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the automatic server card update loop."""
        if self._update_task is not None:
            return

        self._update_task = asyncio.create_task(
            self._update_loop()
        )

        LOGGER.info(
            "Server information update service started."
        )

    async def stop(self) -> None:
        """Stop the automatic server card update loop."""
        if self._update_task is None:
            return

        self._update_task.cancel()

        try:
            await self._update_task
        except asyncio.CancelledError:
            pass

        self._update_task = None

    async def update_all_cards(self) -> None:
        """Update every enabled server information card."""
        for config in self.repository.get_enabled_configs():
            guild = self.bot.get_guild(config.guild_id)

            if guild is None:
                continue

            try:
                await self.update_card(
                    guild,
                    config,
                )
            except Exception:
                LOGGER.exception(
                    "Unexpected error updating server card "
                    "for guild %s.",
                    guild.id,
                )

    async def update_card(
        self,
        guild: discord.Guild,
        config: ServerCardConfig | None = None,
    ) -> bool:
        """Update one server information card."""
        if config is None:
            config = self.repository.get_config(
                guild.id
            )

        if config is None or not config.enabled:
            return False

        channel = guild.get_channel(
            config.channel_id
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            LOGGER.warning(
                "Server information channel %s not found "
                "or is not a text channel in guild %s.",
                config.channel_id,
                guild.id,
            )
            return False

        try:
            message = await channel.fetch_message(
                config.message_id
            )
        except discord.NotFound:
            LOGGER.warning(
                "Server information message %s no longer exists "
                "in guild %s.",
                config.message_id,
                guild.id,
            )
            return False
        except discord.Forbidden:
            LOGGER.error(
                "Missing permission to access server information "
                "message in guild %s.",
                guild.id,
            )
            return False
        except discord.HTTPException:
            LOGGER.exception(
                "Discord rejected the request for server information "
                "message in guild %s.",
                guild.id,
            )
            return False

        embed = self.build_embed(guild)

        try:
            await message.edit(
                embed=embed,
            )
        except discord.Forbidden:
            LOGGER.error(
                "Missing permission to edit server information "
                "message %s in guild %s.",
                message.id,
                guild.id,
            )
            return False
        except discord.HTTPException:
            LOGGER.exception(
                "Discord rejected server information message update "
                "in guild %s.",
                guild.id,
            )
            return False

        return True

    async def activate(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
    ) -> discord.Message:
        """Create or replace the permanent server information card."""
        existing_config = self.repository.get_config(
            guild.id
        )

        if existing_config is not None:
            existing_channel = guild.get_channel(
                existing_config.channel_id
            )

            if isinstance(
                existing_channel,
                discord.TextChannel,
            ):
                try:
                    existing_message = (
                        await existing_channel.fetch_message(
                            existing_config.message_id
                        )
                    )

                    embed = self.build_embed(
                        guild
                    )

                    if existing_channel.id != channel.id:
                        await existing_message.delete()
                    else:
                        await existing_message.edit(
                            embed=embed
                        )

                        self.repository.configure(
                            guild_id=guild.id,
                            channel_id=channel.id,
                            message_id=existing_message.id,
                        )

                        return existing_message

                except discord.NotFound:
                    pass

                except discord.Forbidden:
                    LOGGER.warning(
                        "Could not access existing server card "
                        "in guild %s.",
                        guild.id,
                    )

                except discord.HTTPException:
                    LOGGER.exception(
                        "Could not update existing server card "
                        "in guild %s.",
                        guild.id,
                    )

        embed = self.build_embed(
            guild
        )

        message = await channel.send(
            embed=embed,
        )

        self.repository.configure(
            guild_id=guild.id,
            channel_id=channel.id,
            message_id=message.id,
        )

        return message

    def update_setting(
        self,
        guild_id: int,
        key: str,
        value,
    ) -> None:
        """Update one server card setting."""
        settings = self.repository.get_settings(
            guild_id
        )

        settings[key] = value

        self.repository.save_settings(
            guild_id,
            settings,
        )

    def get_settings(
        self,
        guild_id: int,
    ) -> dict:
        """Return server card settings."""
        return self.repository.get_settings(
            guild_id
        )

    def reset_settings(
        self,
        guild_id: int,
    ) -> None:
        """Restore all server card settings."""
        self.repository.reset_settings(
            guild_id
        )

    @staticmethod
    def _parse_color(
        value: str,
    ) -> discord.Color:
        """Convert a hexadecimal color to a Discord color."""
        try:
            normalized = value.strip().lstrip("#")

            if len(normalized) != 6:
                raise ValueError

            return discord.Color(
                int(normalized, 16)
            )

        except (ValueError, TypeError):
            return discord.Color.dark_grey()

    @staticmethod
    def _valid_url(
        value: str | None,
    ) -> bool:
        """Check whether a value is an HTTP(S) URL."""
        if not value:
            return False

        try:
            parsed = urlparse(value)

            return parsed.scheme in {
                "http",
                "https",
            } and bool(parsed.netloc)

        except ValueError:
            return False

    def build_embed(
        self,
        guild: discord.Guild,
    ) -> discord.Embed:
        """Build the current customized server information embed."""
        settings = self.repository.get_settings(
            guild.id
        )

        name = settings.get("name") or guild.name

        description = (
            settings.get("description")
            or "Información actual de este servidor."
        )

        color = self._parse_color(
            settings.get("color")
        )

        embed = discord.Embed(
            title=name[:256],
            description=description[:4096],
            color=color,
        )

        thumbnail_url = settings.get(
            "thumbnail_url"
        )

        if self._valid_url(thumbnail_url):
            embed.set_thumbnail(
                url=thumbnail_url
            )
        elif guild.icon:
            embed.set_thumbnail(
                url=guild.icon.url
            )

        image_url = settings.get(
            "image_url"
        )

        if self._valid_url(image_url):
            embed.set_image(
                url=image_url
            )

        members = guild.members

        total_members = guild.member_count or len(members)

        bots = sum(
            1
            for member in members
            if member.bot
        )

        online_members = sum(
            1
            for member in members
            if not member.bot
            and member.status != discord.Status.offline
        )

        boost_count = guild.premium_subscription_count or 0

        boost_level = (
            str(guild.premium_tier)
            if guild.premium_tier
            else "0"
        )

        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)

        roles = max(
            len(guild.roles) - 1,
            0,
        )

        emojis = len(guild.emojis)
        stickers = len(guild.stickers)

        embed.add_field(
            name="👥 Miembros",
            value=f"{total_members:,}",
            inline=True,
        )

        if settings.get("show_online", True):
            embed.add_field(
                name="🟢 En línea",
                value=f"{online_members:,}",
                inline=True,
            )

        if settings.get("show_bots", True):
            embed.add_field(
                name="🤖 Bots",
                value=f"{bots:,}",
                inline=True,
            )

        if settings.get("show_boosts", True):
            embed.add_field(
                name="💎 Boosts",
                value=f"{boost_count:,}",
                inline=True,
            )

            embed.add_field(
                name="🚀 Nivel de boost",
                value=boost_level,
                inline=True,
            )

        if settings.get("show_channels", True):
            embed.add_field(
                name="📁 Canales",
                value=(
                    f"{text_channels} texto\n"
                    f"{voice_channels} voz\n"
                    f"{categories} categorías"
                ),
                inline=True,
            )

        if settings.get("show_roles", True):
            embed.add_field(
                name="🎭 Roles",
                value=f"{roles:,}",
                inline=True,
            )

        if settings.get("show_emojis", True):
            embed.add_field(
                name="😀 Emojis",
                value=f"{emojis:,}",
                inline=True,
            )

        if settings.get("show_stickers", True):
            embed.add_field(
                name="🎨 Stickers",
                value=f"{stickers:,}",
                inline=True,
            )

        if settings.get("show_owner", True):
            owner = guild.owner

            embed.add_field(
                name="👑 Propietario",
                value=(
                    owner.mention
                    if owner is not None
                    else "No disponible"
                ),
                inline=True,
            )

        if settings.get("show_created", True):
            embed.add_field(
                name="📅 Creado",
                value=discord.utils.format_dt(
                    guild.created_at,
                    style="D",
                ),
                inline=True,
            )

        website = settings.get("website")

        if self._valid_url(website):
            embed.add_field(
                name="🌐 Sitio web",
                value=f"[Visitar sitio web]({website})",
                inline=False,
            )

        embed.set_footer(
            text="⚙️ Potenciado por Odinus • 0D1N SOFTWARE"
        )

        return embed

    async def _update_loop(self) -> None:
        """Periodically refresh all configured server cards."""
        try:
            await self.bot.wait_until_ready()

            while not self.bot.is_closed():
                await self.update_all_cards()

                await asyncio.sleep(
                    UPDATE_INTERVAL
                )

        except asyncio.CancelledError:
            raise

        except Exception:
            LOGGER.exception(
                "Unexpected error in server information "
                "update loop."
            )