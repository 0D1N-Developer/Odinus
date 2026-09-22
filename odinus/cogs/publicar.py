"""Slash command for publishing a message in the current channel."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


class PublicarCog(commands.Cog):
    """Commands for direct Discord publishing."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="publicar",
        description="Publica un mensaje en este canal.",
    )
    @app_commands.describe(mensaje="Texto que se publicará en el canal.")
    async def publicar(self, interaction: discord.Interaction, mensaje: str) -> None:
        """Publish a user-provided message to the invoking channel."""
        if interaction.channel is None:
            await interaction.response.send_message(
                "No pude identificar el canal donde publicar el mensaje.", ephemeral=True
            )
            return

        await interaction.channel.send(mensaje)
        await interaction.response.send_message("Mensaje publicado.", ephemeral=True)
        LOGGER.info(
            "Message published by user_id=%s in channel_id=%s.",
            interaction.user.id,
            interaction.channel_id,
        )


async def setup(bot: commands.Bot) -> None:
    """Register this command module with Odinus."""
    await bot.add_cog(PublicarCog(bot))
