"""Slash command for publishing a message to a selected server channel."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


class PublicarCog(commands.Cog):
    """Commands for administrator-controlled Discord publishing."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="publicar",
        description="Publica un mensaje en un canal del servidor.",
    )
    @app_commands.describe(
        canal="Canal donde se publicará el mensaje.",
        mensaje="Texto que se publicará.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def publicar(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        mensaje: str,
    ) -> None:
        """Publish a message to the selected server text channel."""
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "Este comando solo puede usarse desde un canal privado del servidor.",
                ephemeral=True,
            )
            return

        default_role_permissions = interaction.channel.permissions_for(
            interaction.guild.default_role
        )
        if default_role_permissions.view_channel:
            await interaction.response.send_message(
                "Utiliza este comando desde un canal privado de administración.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        await canal.send(
            mensaje,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=True,
                roles=True,
                replied_user=False,
            ),
        )
        await interaction.edit_original_response(
            content=f"Mensaje publicado en {canal.mention}."
        )
        LOGGER.info(
            "Message published by administrator user_id=%s in channel_id=%s.",
            interaction.user.id,
            canal.id,
        )

    @publicar.error
    async def publicar_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Return a private explanation when an administrator check fails."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "No tienes permiso para utilizar este comando.",
                ephemeral=True,
            )
            LOGGER.warning(
                "Unauthorized /publicar attempt by user_id=%s.", interaction.user.id
            )
            return

        raise error


async def setup(bot: commands.Bot) -> None:
    """Register this command module with Odinus."""
    await bot.add_cog(PublicarCog(bot))
