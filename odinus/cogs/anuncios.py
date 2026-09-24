"""Discord commands for the generic Odinus announcement center."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from odinus.services.anuncios import (
    AnnouncementRepository,
    AnnouncementService,
)


LOGGER = logging.getLogger(__name__)


PLATFORM_LABELS = {
    "minecraft": "Minecraft",
    "blacktibii": "BlackTibii.com",
}


PLATFORM_CHOICES = [
    app_commands.Choice(
        name=label,
        value=platform,
    )
    for platform, label in PLATFORM_LABELS.items()
]


class AnunciosCog(commands.GroupCog, group_name="anuncios"):
    """Manage the generic Odinus announcement center."""

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot
        self.repository = AnnouncementRepository()

        self.service = AnnouncementService(
            bot=bot,
            repository=self.repository,
        )

    async def cog_load(self) -> None:
        """Initialize announcement persistence."""
        self.repository.initialize()

        LOGGER.info(
            "Generic announcement center initialized."
        )

    @app_commands.command(
        name="configurar",
        description="Configura el canal de una fuente de anuncios.",
    )
    @app_commands.describe(
        plataforma="Fuente de anuncios que quieres configurar.",
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
        """Configure an announcement source."""
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

        label = PLATFORM_LABELS[plataforma.value]

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
        description="Activa una fuente de anuncios.",
    )
    @app_commands.describe(
        plataforma="Fuente de anuncios que quieres activar.",
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
        """Enable an announcement source."""
        if interaction.guild is None:
            return

        updated = self.repository.set_enabled(
            guild_id=interaction.guild.id,
            platform=plataforma.value,
            enabled=True,
        )

        label = PLATFORM_LABELS[plataforma.value]

        if not updated:
            await interaction.response.send_message(
                f"⚠️ **{label}** todavía no está configurado.\n"
                "Usa `/anuncios configurar` primero.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"🟢 Los anuncios de **{label}** están activos.",
            ephemeral=True,
        )

    @app_commands.command(
        name="desactivar",
        description="Desactiva una fuente de anuncios.",
    )
    @app_commands.describe(
        plataforma="Fuente de anuncios que quieres desactivar.",
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
        """Disable an announcement source."""
        if interaction.guild is None:
            return

        updated = self.repository.set_enabled(
            guild_id=interaction.guild.id,
            platform=plataforma.value,
            enabled=False,
        )

        label = PLATFORM_LABELS[plataforma.value]

        if not updated:
            await interaction.response.send_message(
                f"⚠️ **{label}** no está configurado.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"🔴 Los anuncios de **{label}** están desactivados.",
            ephemeral=True,
        )

    @app_commands.command(
        name="comprobar",
        description="Comprueba el estado de una fuente de anuncios.",
    )
    @app_commands.describe(
        plataforma="Fuente de anuncios que quieres comprobar.",
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
        """Check the configuration of an announcement source."""
        if interaction.guild is None:
            return

        label = PLATFORM_LABELS[plataforma.value]

        config = self.repository.get_config(
            interaction.guild.id,
            plataforma.value,
        )

        if config is None:
            await interaction.response.send_message(
                f"⚠️ **{label}** no está configurado.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(
            config.channel_id
        )

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                f"⚠️ El canal configurado para **{label}** "
                "ya no existe o no es un canal de texto.",
                ephemeral=True,
            )
            return

        status = (
            "🟢 Activo"
            if config.enabled
            else "🔴 Desactivado"
        )

        await interaction.response.send_message(
            f"📢 **{label}**\n\n"
            f"Estado: {status}\n"
            f"Canal: {channel.mention}\n\n"
            "La comprobación automática de esta fuente "
            "todavía no está implementada. "
            "La arquitectura está preparada para la futura "
            "integración.",
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
        """Show the current announcement configuration."""
        if interaction.guild is None:
            return

        configs = self.repository.get_configs(
            interaction.guild.id
        )

        embed = discord.Embed(
            title="📢 Centro de anuncios",
            description=(
                "Fuentes propias de Odin Software "
                "disponibles para este servidor."
            ),
            color=discord.Color.blurple(),
        )

        if not configs:
            embed.description = (
                "No hay ninguna fuente configurada todavía.\n\n"
                "Fuentes disponibles:\n"
                "• Minecraft\n"
                "• BlackTibii.com"
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
                "❌ Necesitas el permiso "
                "**Administrar servidor** para usar este comando."
            )

        elif isinstance(
            error,
            app_commands.NoPrivateMessage,
        ):
            message = (
                "❌ Este comando solo puede utilizarse dentro de un servidor."
            )

        else:
            LOGGER.exception(
                "Unexpected error in announcement command.",
                exc_info=error,
            )
            message = (
                "❌ Ocurrió un error al ejecutar el comando."
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


async def setup(bot: commands.Bot) -> None:
    """Load the announcement cog."""
    await bot.add_cog(AnunciosCog(bot))
