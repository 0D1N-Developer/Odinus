"""Automatic announcement center for Odinus."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from odinus.config import load_settings
from odinus.integrations.anuncios.base import AnnouncementEvent
from odinus.services.anuncios import (
    AnnouncementRepository,
    AnnouncementService,
)


LOGGER = logging.getLogger(__name__)


PLATFORM_LABELS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "twitch": "Twitch",
    "youtube": "YouTube",
    "spotify": "Spotify",
    "ServerMinecraft": "ServerMinecraft",
}


PLATFORM_CHOICES = [
    app_commands.Choice(
        name=label,
        value=platform,
    )
    for platform, label in PLATFORM_LABELS.items()
]


YOUTUBE_ICON_URL = (
    "https://cdn.simpleicons.org/youtube/FF0000"
)

TWITCH_ICON_URL = (
    "https://cdn.simpleicons.org/twitch/9146FF"
)

INSTAGRAM_ICON_URL = (
    "https://cdn.simpleicons.org/instagram/E4405F"
)

FACEBOOK_ICON_URL = (
    "https://cdn.simpleicons.org/facebook/1877F2"
)

SPOTIFY_ICON_URL = (
    "https://cdn.simpleicons.org/spotify/1DB954"
)


class AnunciosCog(commands.GroupCog, group_name="anuncios"):
    """Manage the Odinus automatic announcement center."""

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot
        self.settings = load_settings()

        self.repository = AnnouncementRepository()

        self.service = AnnouncementService(
            bot=bot,
            settings=self.settings,
            repository=self.repository,
        )

    async def cog_load(self) -> None:
        """Initialize persistence and start automatic polling."""
        self.repository.initialize()

        self.youtube_poller.change_interval(
            seconds=self.settings.youtube_poll_interval
        )

        self.twitch_poller.change_interval(
            seconds=self.settings.twitch_poll_interval
        )

        self.instagram_poller.change_interval(
            seconds=self.settings.instagram_poll_interval
        )

        self.facebook_poller.change_interval(
            seconds=self.settings.facebook_poll_interval
        )

        self.spotify_poller.change_interval(
            seconds=self.settings.spotify_poll_interval
        )

        self.youtube_poller.start()
        self.twitch_poller.start()
        self.instagram_poller.start()
        self.facebook_poller.start()
        self.spotify_poller.start()

        LOGGER.info(
            "YouTube announcement poller started. "
            "Interval: %s seconds.",
            self.settings.youtube_poll_interval,
        )

        LOGGER.info(
            "Twitch announcement poller started. "
            "Interval: %s seconds.",
            self.settings.twitch_poll_interval,
        )

        LOGGER.info(
            "Instagram announcement poller started. "
            "Interval: %s seconds.",
            self.settings.instagram_poll_interval,
        )

        LOGGER.info(
            "Facebook announcement poller started. "
            "Interval: %s seconds.",
            self.settings.facebook_poll_interval,
        )

        LOGGER.info(
            "Spotify announcement poller started. "
            "Interval: %s seconds.",
            self.settings.spotify_poll_interval,
        )

    def cog_unload(self) -> None:
        """Stop background tasks when the cog is unloaded."""
        self.youtube_poller.cancel()
        self.twitch_poller.cancel()
        self.instagram_poller.cancel()
        self.facebook_poller.cancel()
        self.spotify_poller.cancel()

    @tasks.loop(seconds=60)
    async def youtube_poller(self) -> None:
        """Poll YouTube for new content."""
        await self.service.poll_youtube()

    @youtube_poller.before_loop
    async def before_youtube_poller(self) -> None:
        """Wait until Discord is ready before polling."""
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=60)
    async def twitch_poller(self) -> None:
        """Poll Twitch for new live streams."""
        await self.service.poll_twitch()

    @twitch_poller.before_loop
    async def before_twitch_poller(self) -> None:
        """Wait until Discord is ready before polling."""
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=60)
    async def instagram_poller(self) -> None:
        """Poll Instagram for new posts and Reels."""
        await self.service.poll_instagram()

    @instagram_poller.before_loop
    async def before_instagram_poller(self) -> None:
        """Wait until Discord is ready before polling."""
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=60)
    async def facebook_poller(self) -> None:
        """Poll Facebook for new posts and Reels."""
        await self.service.poll_facebook()

    @facebook_poller.before_loop
    async def before_facebook_poller(self) -> None:
        """Wait until Discord is ready before polling."""
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=60)
    async def spotify_poller(self) -> None:
        """Poll Spotify for new releases."""
        await self.service.poll_spotify()

    @spotify_poller.before_loop
    async def before_spotify_poller(self) -> None:
        """Wait until Discord is ready before polling."""
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="configurar",
        description="Configura el canal de una plataforma.",
    )
    @app_commands.describe(
        plataforma="Plataforma que quieres configurar.",
        canal="Canal donde se publicarán los anuncios.",
        mencion="Rol que será mencionado en los anuncios.",
    )
    @app_commands.choices(
        plataforma=PLATFORM_CHOICES,
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def configurar(
        self,
        interaction: discord.Interaction,
        plataforma: app_commands.Choice[str],
        canal: discord.TextChannel,
        mencion: discord.Role | None = None,
    ) -> None:
        """Configure the announcement channel for a platform."""
        if interaction.guild is None:
            return

        self.repository.configure(
            guild_id=interaction.guild.id,
            platform=plataforma.value,
            channel_id=canal.id,
            mention_role_id=(
                mencion.id
                if mencion is not None
                else None
            ),
        )

        label = PLATFORM_LABELS.get(
            plataforma.value,
            plataforma.value,
        )

        mention_text = (
            mencion.mention
            if mencion is not None
            else "Sin mención"
        )

        await interaction.response.send_message(
            f"✅ **{label}** configurado correctamente.\n"
            f"📢 Canal: {canal.mention}\n"
            f"🔔 Mención: {mention_text}",
            ephemeral=True,
        )

    @app_commands.command(
        name="activar",
        description="Activa los anuncios de una plataforma.",
    )
    @app_commands.describe(
        plataforma="Plataforma que quieres activar.",
    )
    @app_commands.choices(
        plataforma=PLATFORM_CHOICES,
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def activar(
        self,
        interaction: discord.Interaction,
        plataforma: app_commands.Choice[str],
    ) -> None:
        """Enable an announcement integration."""
        if interaction.guild is None:
            return

        updated = self.repository.set_enabled(
            guild_id=interaction.guild.id,
            platform=plataforma.value,
            enabled=True,
        )

        if not updated:
            await interaction.response.send_message(
                "❌ Esa plataforma todavía no está configurada.",
                ephemeral=True,
            )
            return

        label = PLATFORM_LABELS.get(
            plataforma.value,
            plataforma.value,
        )

        await interaction.response.send_message(
            f"✅ Anuncios de **{label}** activados.",
            ephemeral=True,
        )

    @app_commands.command(
        name="desactivar",
        description="Desactiva los anuncios de una plataforma.",
    )
    @app_commands.describe(
        plataforma="Plataforma que quieres desactivar.",
    )
    @app_commands.choices(
        plataforma=PLATFORM_CHOICES,
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def desactivar(
        self,
        interaction: discord.Interaction,
        plataforma: app_commands.Choice[str],
    ) -> None:
        """Disable an announcement integration."""
        if interaction.guild is None:
            return

        updated = self.repository.set_enabled(
            guild_id=interaction.guild.id,
            platform=plataforma.value,
            enabled=False,
        )

        if not updated:
            await interaction.response.send_message(
                "❌ Esa plataforma todavía no está configurada.",
                ephemeral=True,
            )
            return

        label = PLATFORM_LABELS.get(
            plataforma.value,
            plataforma.value,
        )

        await interaction.response.send_message(
            f"⏸️ Anuncios de **{label}** desactivados.",
            ephemeral=True,
        )

    @app_commands.command(
        name="comprobar",
        description="Comprueba manualmente si hay contenido nuevo.",
    )
    @app_commands.describe(
        plataforma="Plataforma que quieres comprobar.",
    )
    @app_commands.choices(
        plataforma=PLATFORM_CHOICES,
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def comprobar(
        self,
        interaction: discord.Interaction,
        plataforma: app_commands.Choice[str],
    ) -> None:
        """Manually check an announcement integration."""
        if interaction.guild is None:
            return

        if plataforma.value not in (
            "youtube",
            "twitch",
            "instagram",
            "facebook",
            "spotify",
        ):
            await interaction.response.send_message(
                "⚠️ Por ahora la comprobación manual "
                "solo está disponible para YouTube, Twitch, "
                "Instagram, Facebook y Spotify.",
                ephemeral=True,
            )
            return

        platform = plataforma.value
        label = PLATFORM_LABELS[platform]

        config = self.repository.get_config(
            interaction.guild.id,
            platform,
        )

        if config is None:
            await interaction.response.send_message(
                f"❌ {label} todavía no está configurado "
                "en este servidor.",
                ephemeral=True,
            )
            return

        if not config.enabled:
            await interaction.response.send_message(
                f"⏸️ Los anuncios de {label} están desactivados.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(
            config.channel_id
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            await interaction.response.send_message(
                f"❌ El canal configurado para {label} "
                "no existe o no es un canal de texto.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        try:
            if platform == "youtube":
                events = await self.service.youtube.fetch_events()

            elif platform == "twitch":
                events = await self.service.twitch.fetch_events()

            elif platform == "instagram":
                events = await self.service.instagram.fetch_events()

            elif platform == "facebook":
                events = await self.service.facebook.fetch_events()

            else:
                events = await self.service.spotify.fetch_events()

        except Exception:
            LOGGER.exception(
                "Manual %s check failed.",
                platform,
            )

            await interaction.followup.send(
                f"❌ Ocurrió un error al consultar {label}.",
                ephemeral=True,
            )
            return

        if not events:
            if platform == "twitch":
                await self._send_twitch_preview(
                    interaction,
                    "ℹ️ El canal de Twitch no está "
                    "en directo actualmente.\n\n"
                    "👁️ **Vista previa del anuncio:**",
                )
                return

            if platform == "instagram":
                await self._send_instagram_preview(
                    interaction,
                    "ℹ️ Instagram no devolvió contenido nuevo.\n\n"
                    "👁️ **Vista previa del anuncio:**",
                )
                return

            if platform == "facebook":
                await self._send_facebook_preview(
                    interaction,
                    "ℹ️ Facebook no devolvió contenido nuevo.\n\n"
                    "👁️ **Vista previa del anuncio:**",
                )
                return

            if platform == "spotify":
                await self._send_spotify_preview(
                    interaction,
                    "ℹ️ Spotify no devolvió lanzamientos nuevos.\n\n"
                    "👁️ **Vista previa del anuncio:**",
                )
                return

            await self._send_youtube_preview(
                interaction,
                "ℹ️ YouTube no devolvió contenido.\n\n"
                "👁️ **Vista previa del anuncio:**",
            )
            return

        new_events = 0

        for event in reversed(events):
            if self.repository.event_exists(
                interaction.guild.id,
                platform,
                event.external_id,
            ):
                continue

            await self.service._publish_event(
                interaction.guild,
                channel,
                config,
                event,
            )

            if self.repository.event_exists(
                interaction.guild.id,
                platform,
                event.external_id,
            ):
                new_events += 1

        if new_events == 0:
            if platform == "twitch":
                await self._send_twitch_preview(
                    interaction,
                    "✅ **Comprobación completada.** "
                    "No hay un stream nuevo.\n\n"
                    "👁️ **Vista previa del anuncio:**",
                )
                return

            if platform == "instagram":
                await self._send_instagram_preview(
                    interaction,
                    "✅ **Comprobación completada.** "
                    "No hay contenido nuevo.\n\n"
                    "👁️ **Vista previa del anuncio:**",
                )
                return

            if platform == "facebook":
                await self._send_facebook_preview(
                    interaction,
                    "✅ **Comprobación completada.** "
                    "No hay contenido nuevo.\n\n"
                    "👁️ **Vista previa del anuncio:**",
                )
                return

            if platform == "spotify":
                await self._send_spotify_preview(
                    interaction,
                    "✅ **Comprobación completada.** "
                    "No hay lanzamientos nuevos.\n\n"
                    "👁️ **Vista previa del anuncio:**",
                )
                return

            await self._send_youtube_preview(
                interaction,
                "✅ **Comprobación completada.** "
                "No hay contenido nuevo.\n\n"
                "👁️ **Vista previa del anuncio:**",
            )
            return

        await interaction.followup.send(
            f"✅ **Comprobación completada.** "
            f"Se publicaron **{new_events}** anuncio(s).",
            ephemeral=True,
        )

    async def _send_spotify_preview(
        self,
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        """Send the Spotify announcement preview."""
        preview_event = AnnouncementEvent(
            platform="spotify",
            external_id="preview",
            event_type="single",
            title=(
                "Mi nuevo sencillo — Ejemplo"
            ),
            url=(
                "https://open.spotify.com/"
            ),
            description=(
                "Black Tibii lanzó "
                "“Mi nuevo sencillo — Ejemplo” "
                "en Spotify.\n\n"
                "Tipo: Sencillo\n"
                "Canciones: 1\n"
                "Fecha de lanzamiento: 23/09/2026"
            ),
            thumbnail_url=(
                "https://placehold.co/1000x1000/png"
                "?text=SPOTIFY+COVER"
            ),
            image_url=(
                "https://placehold.co/256x256/png"
                "?text=BLACK+TIBII"
            ),
            published_at="2026-09-23",
            author_name="Black Tibii",
            author_icon_url=(
                "https://placehold.co/256x256/png"
                "?text=BLACK+TIBII"
            ),
            platform_icon_url=SPOTIFY_ICON_URL,
        )

        preview_embed = self.service._build_embed(
            preview_event,
            "Black Tibii",
            "Spotify",
            (
                "Black Tibii lanzó un nuevo "
                "sencillo en Spotify."
            ),
            discord.Color.from_rgb(
                29,
                185,
                84,
            ),
        )

        preview_content = (
            "@here 💀 Black Tibii lanzó nueva música! 🎵\n\n"
            "Mi nuevo sencillo — Ejemplo\n\n"
            "🔗 [Escuchar en Spotify]"
            "(https://open.spotify.com/)"
        )

        await interaction.followup.send(
            content=(
                f"{message}\n\n"
                f"{preview_content}"
            ),
            embed=preview_embed,
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )

    async def _send_twitch_preview(
        self,
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        """Send the Twitch announcement preview."""
        preview_event = AnnouncementEvent(
            platform="twitch",
            external_id="preview",
            event_type="live",
            title="Mi stream en vivo — Ejemplo",
            url="https://www.twitch.tv/ejemplo",
            description=(
                "Just Chatting • "
                "123 espectadores"
            ),
            thumbnail_url=(
                "https://placehold.co/1280x720/png"
                "?text=TWITCH+LIVE"
            ),
            image_url=(
                "https://placehold.co/285x380/png"
                "?text=GAME+COVER"
            ),
            published_at=datetime.now(
                timezone.utc
            ).isoformat(),
            author_name="Black Tibii",
            author_icon_url=(
                "https://placehold.co/256x256/png"
                "?text=BLACK+TIBII"
            ),
            platform_icon_url=TWITCH_ICON_URL,
        )

        preview_embed = self.service._build_embed(
            preview_event,
            "Black Tibii",
            "Twitch",
            "Black Tibii está en directo en Twitch.",
            discord.Color.purple(),
        )

        preview_content = (
            "@here 💀 Black Tibii está en directo!\n\n"
            "Mi stream en vivo — Ejemplo\n\n"
            "🔗 [Ver en Twitch]"
            "(https://www.twitch.tv/ejemplo)"
        )

        await interaction.followup.send(
            content=(
                f"{message}\n\n"
                f"{preview_content}"
            ),
            embed=preview_embed,
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )

    async def _send_instagram_preview(
        self,
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        """Send the Instagram announcement preview."""
        preview_event = AnnouncementEvent(
            platform="instagram",
            external_id="preview",
            event_type="post",
            title=(
                "Black Tibii publicó una nueva publicación."
            ),
            url="https://www.instagram.com/",
            description=(
                "Esta es una descripción de ejemplo "
                "para comprobar cómo se verá una "
                "publicación de Instagram."
            ),
            thumbnail_url=(
                "https://placehold.co/1280x720/png"
                "?text=INSTAGRAM+POST"
            ),
            image_url=(
                "https://placehold.co/256x256/png"
                "?text=BLACK+TIBII"
            ),
            published_at=datetime.now(
                timezone.utc
            ).isoformat(),
            author_name="Black Tibii",
            author_icon_url=(
                "https://placehold.co/256x256/png"
                "?text=BLACK+TIBII"
            ),
            platform_icon_url=INSTAGRAM_ICON_URL,
        )

        preview_embed = self.service._build_embed(
            preview_event,
            "Black Tibii",
            "Instagram",
            (
                "Black Tibii publicó una nueva "
                "publicación en Instagram."
            ),
            discord.Color.magenta(),
        )

        preview_content = (
            "@here 💀 Black Tibii publicó algo nuevo! 📸\n\n"
            "Nueva publicación — "
            "#BlackTibii #Rock #Music\n\n"
            "🔗 [Ver en Instagram]"
            "(https://www.instagram.com/)"
        )

        await interaction.followup.send(
            content=(
                f"{message}\n\n"
                f"{preview_content}"
            ),
            embed=preview_embed,
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )

    async def _send_facebook_preview(
        self,
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        """Send the Facebook announcement preview."""
        preview_event = AnnouncementEvent(
            platform="facebook",
            external_id="preview",
            event_type="post",
            title=(
                "Black Tibii publicó una nueva publicación."
            ),
            url="https://www.facebook.com/",
            description=(
                "Esta es una descripción de ejemplo "
                "para comprobar cómo se verá una "
                "publicación de Facebook."
            ),
            thumbnail_url=(
                "https://placehold.co/1280x720/png"
                "?text=FACEBOOK+POST"
            ),
            image_url=(
                "https://placehold.co/256x256/png"
                "?text=BLACK+TIBII"
            ),
            published_at=datetime.now(
                timezone.utc
            ).isoformat(),
            author_name="Black Tibii",
            author_icon_url=(
                "https://placehold.co/256x256/png"
                "?text=BLACK+TIBII"
            ),
            platform_icon_url=FACEBOOK_ICON_URL,
        )

        preview_embed = self.service._build_embed(
            preview_event,
            "Black Tibii",
            "Facebook",
            (
                "Black Tibii publicó una nueva "
                "publicación en Facebook."
            ),
            discord.Color.blue(),
        )

        preview_content = (
            "@here 💀 Black Tibii publicó algo nuevo! 📘\n\n"
            "Nueva publicación — "
            "#BlackTibii #Rock #Music\n\n"
            "🔗 [Ver en Facebook]"
            "(https://www.facebook.com/)"
        )

        await interaction.followup.send(
            content=(
                f"{message}\n\n"
                f"{preview_content}"
            ),
            embed=preview_embed,
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )

    async def _send_youtube_preview(
        self,
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        """Send the YouTube announcement preview."""
        preview_event = AnnouncementEvent(
            platform="youtube",
            external_id="preview",
            event_type="video",
            title=(
                "Mi nuevo video — "
                "Ejemplo #BlackTibii #Music"
            ),
            url=(
                "https://www.youtube.com/watch?v=ejemplo"
            ),
            description=(
                "Esta es una descripción de ejemplo "
                "para comprobar cómo se verá el anuncio "
                "cuando se publique un video real."
            ),
            thumbnail_url=(
                "https://placehold.co/1280x720/png"
                "?text=MINIATURA+DE+EJEMPLO"
            ),
            image_url=(
                "https://placehold.co/256x256/png"
                "?text=BLACK+TIBII"
            ),
            published_at=datetime.now(
                timezone.utc
            ).isoformat(),
            author_name="Black Tibii",
            author_icon_url=(
                "https://placehold.co/256x256/png"
                "?text=BLACK+TIBII"
            ),
            platform_icon_url=YOUTUBE_ICON_URL,
        )

        preview_embed = self.service._build_embed(
            preview_event,
            "Black Tibii",
            "YouTube",
            "Black Tibii publicó un nuevo video en YouTube.",
            discord.Color.red(),
        )

        preview_content = (
            "@here 💀 Black Tibii ha subido "
            "un nuevo video! 📹\n\n"
            "Mi nuevo video — "
            "Ejemplo #BlackTibii #Music\n\n"
            "🔗 [Ver en YouTube]"
            "(https://www.youtube.com/watch?v=ejemplo)"
        )

        await interaction.followup.send(
            content=(
                f"{message}\n\n"
                f"{preview_content}"
            ),
            embed=preview_embed,
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )

    @app_commands.command(
        name="estado",
        description="Muestra la configuración del centro de anuncios.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def estado(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Show every configured announcement integration."""
        if interaction.guild is None:
            return

        configs = self.repository.get_configs(
            interaction.guild.id
        )

        if not configs:
            await interaction.response.send_message(
                "📢 No hay ninguna plataforma configurada todavía.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📢 Centro de anuncios",
            description=(
                "Configuración actual de las "
                "integraciones de Odinus."
            ),
            color=discord.Color.blurple(),
        )

        for config in configs:
            label = PLATFORM_LABELS.get(
                config.platform,
                config.platform,
            )

            channel = interaction.guild.get_channel(
                config.channel_id
            )

            channel_text = (
                channel.mention
                if channel is not None
                else f"`{config.channel_id}`"
            )

            role = (
                interaction.guild.get_role(
                    config.mention_role_id
                )
                if config.mention_role_id is not None
                else None
            )

            mention_text = (
                role.mention
                if role is not None
                else "Sin mención"
            )

            status = (
                "🟢 Activo"
                if config.enabled
                else "🔴 Desactivado"
            )

            embed.add_field(
                name=label,
                value=(
                    f"{status}\n"
                    f"📢 {channel_text}\n"
                    f"🔔 {mention_text}"
                ),
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @configurar.error
    @activar.error
    @desactivar.error
    @comprobar.error
    @estado.error
    async def anuncios_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle announcement command errors."""
        if isinstance(
            error,
            app_commands.MissingPermissions,
        ):
            message = (
                "❌ Necesitas permisos de "
                "**Administrar servidor** para utilizar "
                "este comando."
            )

            if interaction.response.is_done():
                await interaction.followup.send(
                    message,
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    message,
                    ephemeral=True,
                )

            return

        LOGGER.exception(
            "Unexpected announcement command error.",
            exc_info=error,
        )

        if interaction.response.is_done():
            await interaction.followup.send(
                "❌ Ocurrió un error al ejecutar el comando.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "❌ Ocurrió un error al ejecutar el comando.",
                ephemeral=True,
            )


async def setup(
    bot: commands.Bot,
) -> None:
    """Load the announcement center cog."""
    await bot.add_cog(
        AnunciosCog(bot)
    )