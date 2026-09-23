"""Profile and rank card commands for Odinus."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from odinus.services.perfil import ProfileService
from odinus.services.rank_card import generate_rank_card


LOGGER = logging.getLogger(__name__)


class PerfilCog(commands.Cog):
    """Commands for member profiles."""

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot
        self.profile_service = ProfileService()

    @app_commands.command(
        name="perfil",
        description="Muestra el perfil completo de un miembro.",
    )
    @app_commands.describe(
        usuario="Miembro cuyo perfil deseas consultar.",
    )
    @app_commands.guild_only()
    async def perfil(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member | None = None,
    ) -> None:
        """Show a complete visual profile."""
        if interaction.guild is None:
            return

        member = usuario or interaction.user

        if not isinstance(
            member,
            discord.Member,
        ):
            await interaction.response.send_message(
                "No pude obtener la información de ese miembro.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            profile = self.profile_service.get_profile(
                guild=interaction.guild,
                member=member,
            )

            card = await generate_rank_card(
                profile
            )

            file = discord.File(
                card,
                filename="odinus-perfil.png",
            )

            await interaction.followup.send(
                file=file,
            )

        except discord.NotFound:
            await interaction.followup.send(
                "❌ No pude obtener el avatar de ese usuario.",
                ephemeral=True,
            )

        except discord.HTTPException:
            LOGGER.exception(
                "Discord error while generating profile "
                "guild=%s user=%s.",
                interaction.guild.id,
                member.id,
            )

            await interaction.followup.send(
                "❌ No pude generar el perfil en este momento.",
                ephemeral=True,
            )

        except Exception:
            LOGGER.exception(
                "Unexpected profile generation error "
                "guild=%s user=%s.",
                interaction.guild.id,
                member.id,
            )

            await interaction.followup.send(
                "❌ Ocurrió un error al generar el perfil.",
                ephemeral=True,
            )


async def setup(
    bot: commands.Bot,
) -> None:
    """Load the profile cog."""
    await bot.add_cog(
        PerfilCog(bot)
    )