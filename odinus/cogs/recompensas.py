"""Level reward administration for Odinus."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from odinus.services.recompensas import RewardService


LOGGER = logging.getLogger(__name__)

MAX_LEVEL = 1000


class RewardCog(commands.Cog):
    """Administration commands for level rewards."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.reward_service = RewardService()

    recompensa = app_commands.Group(
        name="recompensa",
        description="Administra las recompensas por nivel.",
    )

    @recompensa.command(
        name="añadir",
        description="Añade un rol como recompensa de nivel.",
    )
    @app_commands.describe(
        nivel="Nivel que otorgará la recompensa.",
        rol="Rol de Discord que se entregará al alcanzar el nivel.",
        emoji="Emoji asociado a la recompensa.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def recompensa_añadir(
        self,
        interaction: discord.Interaction,
        nivel: app_commands.Range[int, 1, MAX_LEVEL],
        rol: discord.Role,
        emoji: str = "",
    ) -> None:
        """Create a new level reward using an existing Discord role."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Este comando solamente puede utilizarse dentro de un servidor.",
                ephemeral=True,
            )
            return

        emoji = emoji.strip()

        if len(emoji) > 20:
            await interaction.response.send_message(
                "❌ El emoji indicado es demasiado largo.",
                ephemeral=True,
            )
            return

        existing_reward = self.reward_service.get_reward(
            interaction.guild.id,
            nivel,
        )

        if existing_reward is not None:
            await interaction.response.send_message(
                (
                    f"❌ Ya existe una recompensa configurada para el "
                    f"nivel **{nivel}**.\n\n"
                    f"Rol actual: <@&{existing_reward.role_id}>"
                ),
                ephemeral=True,
            )
            return

        # Odinus must be able to manage the selected role.
        bot_member = interaction.guild.me

        if bot_member is None:
            await interaction.response.send_message(
                "❌ No pude obtener la información de Odinus en este servidor.",
                ephemeral=True,
            )
            return

        if rol.is_default():
            await interaction.response.send_message(
                "❌ No puedes utilizar @everyone como recompensa.",
                ephemeral=True,
            )
            return

        if rol.managed:
            await interaction.response.send_message(
                (
                    "❌ Ese rol está administrado por una integración de Discord "
                    "y no puede ser gestionado por Odinus."
                ),
                ephemeral=True,
            )
            return

        if rol >= bot_member.top_role:
            await interaction.response.send_message(
                (
                    "❌ No puedo administrar ese rol porque está por encima "
                    "o al mismo nivel que mi rol más alto.\n\n"
                    "Mueve el rol de Odinus por encima de la recompensa "
                    "que quieras utilizar."
                ),
                ephemeral=True,
            )
            return

        try:
            self.reward_service.create_reward(
                guild_id=interaction.guild.id,
                level=nivel,
                role_id=rol.id,
                role_name=rol.name,
                emoji=emoji,
            )

        except ValueError as error:
            await interaction.response.send_message(
                f"❌ {error}",
                ephemeral=True,
            )
            return

        except Exception:
            LOGGER.exception(
                "Unexpected error while creating level reward.",
            )

            await interaction.response.send_message(
                "❌ Ocurrió un error inesperado al crear la recompensa.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🏆 Recompensa añadida",
            description=(
                f"La recompensa del nivel **{nivel}** ha sido configurada."
            ),
            color=discord.Color.gold(),
        )

        embed.add_field(
            name="Nivel",
            value=f"**{nivel}**",
            inline=True,
        )

        embed.add_field(
            name="Rol",
            value=rol.mention,
            inline=True,
        )

        embed.add_field(
            name="Emoji",
            value=emoji or "Sin emoji",
            inline=True,
        )

        embed.set_footer(
            text="Odinus • El rol fue seleccionado directamente desde Discord.",
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

        LOGGER.info(
            "Level reward created: guild=%s level=%s role=%s role_id=%s",
            interaction.guild.id,
            nivel,
            rol.name,
            rol.id,
        )

    @recompensa.command(
        name="editar",
        description="Edita una recompensa existente.",
    )
    @app_commands.describe(
        nivel="Nivel cuya recompensa deseas editar.",
        rol="Nuevo rol de Discord para la recompensa.",
        emoji="Nuevo emoji asociado a la recompensa.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def recompensa_editar(
        self,
        interaction: discord.Interaction,
        nivel: app_commands.Range[int, 1, MAX_LEVEL],
        rol: discord.Role,
        emoji: str = "",
    ) -> None:
        """Edit an existing level reward."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Este comando solamente puede utilizarse dentro de un servidor.",
                ephemeral=True,
            )
            return

        emoji = emoji.strip()

        if len(emoji) > 20:
            await interaction.response.send_message(
                "❌ El emoji indicado es demasiado largo.",
                ephemeral=True,
            )
            return

        reward = self.reward_service.get_reward(
            interaction.guild.id,
            nivel,
        )

        if reward is None:
            await interaction.response.send_message(
                (
                    f"❌ No existe ninguna recompensa configurada "
                    f"para el nivel **{nivel}**."
                ),
                ephemeral=True,
            )
            return

        bot_member = interaction.guild.me

        if bot_member is None:
            await interaction.response.send_message(
                "❌ No pude obtener la información de Odinus en este servidor.",
                ephemeral=True,
            )
            return

        if rol.is_default():
            await interaction.response.send_message(
                "❌ No puedes utilizar @everyone como recompensa.",
                ephemeral=True,
            )
            return

        if rol.managed:
            await interaction.response.send_message(
                (
                    "❌ Ese rol está administrado por una integración de Discord "
                    "y no puede ser gestionado por Odinus."
                ),
                ephemeral=True,
            )
            return

        if rol >= bot_member.top_role:
            await interaction.response.send_message(
                (
                    "❌ No puedo administrar ese rol porque está por encima "
                    "o al mismo nivel que mi rol más alto."
                ),
                ephemeral=True,
            )
            return

        try:
            self.reward_service.update_reward(
                guild_id=interaction.guild.id,
                level=nivel,
                role_id=rol.id,
                role_name=rol.name,
                emoji=emoji,
            )

        except ValueError as error:
            await interaction.response.send_message(
                f"❌ {error}",
                ephemeral=True,
            )
            return

        except Exception:
            LOGGER.exception(
                "Unexpected error while updating level reward.",
            )

            await interaction.response.send_message(
                "❌ Ocurrió un error inesperado al editar la recompensa.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="✏️ Recompensa actualizada",
            description=(
                f"La recompensa del nivel **{nivel}** ha sido actualizada."
            ),
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="Nivel",
            value=f"**{nivel}**",
            inline=True,
        )

        embed.add_field(
            name="Rol",
            value=rol.mention,
            inline=True,
        )

        embed.add_field(
            name="Emoji",
            value=emoji or "Sin emoji",
            inline=True,
        )

        embed.set_footer(
            text="Odinus • Recompensa vinculada por ID de Discord.",
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

        LOGGER.info(
            "Level reward updated: guild=%s level=%s role=%s role_id=%s",
            interaction.guild.id,
            nivel,
            rol.name,
            rol.id,
        )

    @recompensa.command(
        name="eliminar",
        description="Elimina una recompensa de nivel.",
    )
    @app_commands.describe(
        nivel="Nivel cuya recompensa deseas eliminar.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def recompensa_eliminar(
        self,
        interaction: discord.Interaction,
        nivel: app_commands.Range[int, 1, MAX_LEVEL],
    ) -> None:
        """Delete a level reward."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Este comando solamente puede utilizarse dentro de un servidor.",
                ephemeral=True,
            )
            return

        reward = self.reward_service.get_reward(
            interaction.guild.id,
            nivel,
        )

        if reward is None:
            await interaction.response.send_message(
                (
                    f"❌ No existe ninguna recompensa configurada "
                    f"para el nivel **{nivel}**."
                ),
                ephemeral=True,
            )
            return

        deleted = self.reward_service.delete_reward(
            interaction.guild.id,
            nivel,
        )

        if not deleted:
            await interaction.response.send_message(
                "❌ No fue posible eliminar la recompensa.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🗑️ Recompensa eliminada",
            description=(
                f"La recompensa del nivel **{nivel}** ha sido eliminada "
                "de la configuración de Odinus."
            ),
            color=discord.Color.red(),
        )

        embed.add_field(
            name="Rol",
            value=f"<@&{reward.role_id}>",
            inline=False,
        )

        embed.set_footer(
            text=(
                "El rol de Discord no se elimina. "
                "Odinus tampoco elimina roles automáticamente."
            )
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

        LOGGER.info(
            "Level reward deleted: guild=%s level=%s role_id=%s",
            interaction.guild.id,
            nivel,
            reward.role_id,
        )

    @recompensa.command(
        name="lista",
        description="Muestra las recompensas configuradas.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def recompensa_lista(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Display all configured level rewards."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Este comando solamente puede utilizarse dentro de un servidor.",
                ephemeral=True,
            )
            return

        rewards = self.reward_service.get_rewards(
            interaction.guild.id,
        )

        if not rewards:
            await interaction.response.send_message(
                (
                    "🏆 **Recompensas por nivel**\n\n"
                    "Todavía no hay recompensas configuradas."
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🏆 Recompensas por nivel",
            description=(
                f"Hay **{len(rewards)}** recompensa(s) configurada(s)."
            ),
            color=discord.Color.gold(),
        )

        lines: list[str] = []

        for reward in rewards:
            role = interaction.guild.get_role(
                reward.role_id,
            )

            if role is not None:
                role_display = role.mention
            else:
                role_display = (
                    f"`{reward.role_name}` "
                    "(rol no encontrado)"
                )

            emoji_display = reward.emoji or "▫️"

            lines.append(
                f"{emoji_display} **Nivel {reward.level}** → "
                f"{role_display}"
            )

        description = "\n".join(lines)

        if len(description) > 4000:
            description = (
                description[:3990]
                + "\n…"
            )

        embed.add_field(
            name="Configuración",
            value=description,
            inline=False,
        )

        embed.set_footer(
            text="Odinus • Sistema de recompensas",
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @recompensa_añadir.error
    @recompensa_editar.error
    @recompensa_eliminar.error
    @recompensa_lista.error
    async def recompensa_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle reward command permission errors."""
        if isinstance(
            error,
            app_commands.errors.MissingPermissions,
        ):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    (
                        "❌ No tienes permisos para administrar "
                        "las recompensas por nivel.\n\n"
                        "Necesitas el permiso **Administrador**."
                    ),
                    ephemeral=True,
                )
            return

        LOGGER.exception(
            "Unhandled reward command error.",
            exc_info=error,
        )

        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ Ocurrió un error al ejecutar el comando.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    """Load the reward cog."""
    await bot.add_cog(
        RewardCog(bot)
    )