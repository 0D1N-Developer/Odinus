"""Leveling Cog for Odinus."""

from __future__ import annotations

import logging
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from odinus.services.niveles import (
    MAX_LEVEL,
    MAX_XP_PER_MESSAGE,
    MIN_XP_PER_MESSAGE,
    LevelService,
)
from odinus.services.recompensas import (
    LevelReward,
    RewardService,
)


LOGGER = logging.getLogger(__name__)

LEADERBOARD_PAGE_SIZE = 10


class LevelView(discord.ui.View):
    """View displayed below the user's level information."""

    def __init__(
        self,
        cog: "Niveles",
        owner_id: int,
        guild_id: int,
        target_id: int,
    ) -> None:
        super().__init__(timeout=180)

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.target_id = target_id

    @discord.ui.button(
        label="Ver ranking",
        emoji="Ã°Å¸Ââ€ ",
        style=discord.ButtonStyle.primary,
    )
    async def ranking_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Open the server leaderboard."""
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ Solo la persona que ejecutÃƒÂ³ este comando "
                "puede utilizar estos botones.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=self.cog.create_ranking_embed(
                guild=interaction.guild,
                page=0,
            ),
            view=RankingView(
                cog=self.cog,
                owner_id=self.owner_id,
                guild_id=self.guild_id,
                target_id=self.target_id,
                page=0,
            ),
        )


class RankingView(discord.ui.View):
    """Paginated leaderboard controls."""

    def __init__(
        self,
        cog: "Niveles",
        owner_id: int,
        guild_id: int,
        target_id: int,
        page: int = 0,
    ) -> None:
        super().__init__(timeout=180)

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.target_id = target_id
        self.page = page

        self._update_buttons()

    def _update_buttons(self) -> None:
        """Enable or disable pagination buttons."""
        total_users = self.cog.level_service.repository.count_users(
            self.guild_id
        )

        total_pages = max(
            1,
            (
                total_users + LEADERBOARD_PAGE_SIZE - 1
            ) // LEADERBOARD_PAGE_SIZE,
        )

        self.previous_button.disabled = self.page <= 0
        self.next_button.disabled = (
            self.page >= total_pages - 1
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """Only allow the command owner to use the view."""
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            "Ã¢ÂÅ’ Solo la persona que ejecutÃƒÂ³ este comando "
            "puede utilizar estos botones.",
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Anterior",
        emoji="Ã¢â€”â‚¬Ã¯Â¸Â",
        style=discord.ButtonStyle.secondary,
    )
    async def previous_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Move to the previous leaderboard page."""
        if self.page > 0:
            self.page -= 1

        self._update_buttons()

        await interaction.response.edit_message(
            embed=self.cog.create_ranking_embed(
                guild=interaction.guild,
                page=self.page,
            ),
            view=self,
        )

    @discord.ui.button(
        label="Mi nivel",
        emoji="Ã°Å¸â€˜Â¤",
        style=discord.ButtonStyle.primary,
    )
    async def profile_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Return to the level profile."""
        await interaction.response.edit_message(
            embed=self.cog.create_level_embed(
                guild=interaction.guild,
                target_id=self.target_id,
            ),
            view=self.cog.create_level_view(
                owner_id=self.owner_id,
                guild_id=self.guild_id,
                target_id=self.target_id,
            ),
        )

    @discord.ui.button(
        label="Siguiente",
        emoji="Ã¢â€“Â¶Ã¯Â¸Â",
        style=discord.ButtonStyle.secondary,
    )
    async def next_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Move to the next leaderboard page."""
        total_users = self.cog.level_service.repository.count_users(
            self.guild_id
        )

        total_pages = max(
            1,
            (
                total_users + LEADERBOARD_PAGE_SIZE - 1
            ) // LEADERBOARD_PAGE_SIZE,
        )

        if self.page < total_pages - 1:
            self.page += 1

        self._update_buttons()

        await interaction.response.edit_message(
            embed=self.cog.create_ranking_embed(
                guild=interaction.guild,
                page=self.page,
            ),
            view=self,
        )


class AdminLevelView(discord.ui.View):
    """Administrative panel for managing a user's level."""

    def __init__(
        self,
        cog: "Niveles",
        admin_id: int,
        guild_id: int,
        target_id: int,
    ) -> None:
        super().__init__(timeout=300)

        self.cog = cog
        self.admin_id = admin_id
        self.guild_id = guild_id
        self.target_id = target_id

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """Only the administrator who opened the panel can use it."""
        if interaction.user.id == self.admin_id:
            return True

        await interaction.response.send_message(
            "Ã¢ÂÅ’ Solo el administrador que abriÃƒÂ³ este panel "
            "puede utilizarlo.",
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Dar XP",
        emoji="Ã¢Å¾â€¢",
        style=discord.ButtonStyle.success,
        row=0,
    )
    async def add_xp_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Open the add XP modal."""
        await interaction.response.send_modal(
            AddXPModal(self.cog, self.target_id)
        )

    @discord.ui.button(
        label="Quitar XP",
        emoji="Ã¢Å¾â€“",
        style=discord.ButtonStyle.danger,
        row=0,
    )
    async def remove_xp_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Open the remove XP modal."""
        await interaction.response.send_modal(
            RemoveXPModal(self.cog, self.target_id)
        )

    @discord.ui.button(
        label="Subir nivel",
        emoji="Ã¢Â¬â€ Ã¯Â¸Â",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def increase_level_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Increase the user's level by one."""
        current = self.cog.level_service.repository.get_user(
            self.guild_id,
            self.target_id,
        )

        if current.level >= MAX_LEVEL:
            await interaction.response.send_message(
                "Ã°Å¸Ââ€  El usuario ya se encuentra en el nivel mÃƒÂ¡ximo.",
                ephemeral=True,
            )
            return

        updated = self.cog.level_service.increase_level(
            guild_id=self.guild_id,
            user_id=self.target_id,
            current_time=time.time(),
        )

        await self.cog._sync_level_rewards(
            guild=interaction.guild,
            user_id=self.target_id,
            previous_level=current.level,
            new_level=updated.level,
        )

        self.cog.log_admin_action(
            action="SUBIR NIVEL",
            guild_id=self.guild_id,
            admin_id=self.admin_id,
            target_id=self.target_id,
            before=current,
            after=updated,
        )

        await interaction.response.edit_message(
            embed=self.cog.create_admin_embed(
                guild=interaction.guild,
                target_id=self.target_id,
                action_message=(
                    f"Ã¢Å“â€¦ Nivel aumentado: "
                    f"**{current.level} Ã¢â€ â€™ {updated.level}**"
                ),
            ),
            view=self,
        )

    @discord.ui.button(
        label="Bajar nivel",
        emoji="Ã¢Â¬â€¡Ã¯Â¸Â",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def decrease_level_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Decrease the user's level by one."""
        current = self.cog.level_service.repository.get_user(
            self.guild_id,
            self.target_id,
        )

        if current.level <= 0:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ El usuario ya se encuentra en el nivel 0.",
                ephemeral=True,
            )
            return

        updated = self.cog.level_service.decrease_level(
            guild_id=self.guild_id,
            user_id=self.target_id,
            current_time=time.time(),
        )

        await self.cog._sync_level_rewards(
            guild=interaction.guild,
            user_id=self.target_id,
            previous_level=current.level,
            new_level=updated.level,
        )

        self.cog.log_admin_action(
            action="BAJAR NIVEL",
            guild_id=self.guild_id,
            admin_id=self.admin_id,
            target_id=self.target_id,
            before=current,
            after=updated,
        )

        await interaction.response.edit_message(
            embed=self.cog.create_admin_embed(
                guild=interaction.guild,
                target_id=self.target_id,
                action_message=(
                    f"Ã¢Å“â€¦ Nivel reducido: "
                    f"**{current.level} Ã¢â€ â€™ {updated.level}**"
                ),
            ),
            view=self,
        )

    @discord.ui.button(
        label="Resetear",
        emoji="Ã°Å¸â€â€ž",
        style=discord.ButtonStyle.danger,
        row=2,
    )
    async def reset_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Open reset confirmation."""
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Ã¢Å¡Â Ã¯Â¸Â Confirmar reset",
                description=(
                    f"Ã‚Â¿Seguro que quieres resetear completamente "
                    f"a <@{self.target_id}>?\n\n"
                    "Esto establecerÃƒÂ¡:\n"
                    "Ã¢â‚¬Â¢ Nivel: **0**\n"
                    "Ã¢â‚¬Â¢ XP: **0**\n"
                    "Ã¢â‚¬Â¢ Recompensas de nivel: **se retirarÃƒÂ¡n**\n\n"
                    "Esta acciÃƒÂ³n no puede deshacerse automÃƒÂ¡ticamente."
                ),
                color=discord.Color.red(),
            ),
            view=ResetConfirmationView(
                cog=self.cog,
                admin_id=self.admin_id,
                guild_id=self.guild_id,
                target_id=self.target_id,
                parent_view=self,
            ),
            ephemeral=True,
        )


class AddXPModal(discord.ui.Modal, title="Ã¢Å¾â€¢ Dar experiencia"):
    """Modal for adding XP."""

    amount = discord.ui.TextInput(
        label="Cantidad de XP",
        placeholder="Ejemplo: 500",
        required=True,
        min_length=1,
        max_length=10,
    )

    def __init__(
        self,
        cog: "Niveles",
        target_id: int,
    ) -> None:
        super().__init__()

        self.cog = cog
        self.target_id = target_id

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Process the XP addition."""
        try:
            amount = int(self.amount.value)
        except ValueError:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ Debes introducir una cantidad numÃƒÂ©rica vÃƒÂ¡lida.",
                ephemeral=True,
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ La cantidad debe ser mayor que 0.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        current = self.cog.level_service.repository.get_user(
            guild.id,
            self.target_id,
        )

        updated, _ = self.cog.level_service.add_xp(
            guild_id=guild.id,
            user_id=self.target_id,
            xp_amount=amount,
            current_time=time.time(),
        )

        await self.cog._sync_level_rewards(
            guild=guild,
            user_id=self.target_id,
            previous_level=current.level,
            new_level=updated.level,
        )

        self.cog.log_admin_action(
            action=f"DAR {amount} XP",
            guild_id=guild.id,
            admin_id=interaction.user.id,
            target_id=self.target_id,
            before=current,
            after=updated,
        )

        await interaction.response.send_message(
            embed=self.cog.create_admin_embed(
                guild=guild,
                target_id=self.target_id,
                action_message=(
                    f"Ã¢Å“â€¦ Se otorgaron **{amount:,} XP**."
                ),
            ),
            view=AdminLevelView(
                cog=self.cog,
                admin_id=interaction.user.id,
                guild_id=guild.id,
                target_id=self.target_id,
            ),
            ephemeral=True,
        )


class RemoveXPModal(discord.ui.Modal, title="Ã¢Å¾â€“ Quitar experiencia"):
    """Modal for removing XP."""

    amount = discord.ui.TextInput(
        label="Cantidad de XP",
        placeholder="Ejemplo: 500",
        required=True,
        min_length=1,
        max_length=10,
    )

    def __init__(
        self,
        cog: "Niveles",
        target_id: int,
    ) -> None:
        super().__init__()

        self.cog = cog
        self.target_id = target_id

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Process the XP removal."""
        try:
            amount = int(self.amount.value)
        except ValueError:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ Debes introducir una cantidad numÃƒÂ©rica vÃƒÂ¡lida.",
                ephemeral=True,
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ La cantidad debe ser mayor que 0.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        current = self.cog.level_service.repository.get_user(
            guild.id,
            self.target_id,
        )

        updated, _ = self.cog.level_service.remove_xp(
            guild_id=guild.id,
            user_id=self.target_id,
            xp_amount=amount,
            current_time=time.time(),
        )

        await self.cog._sync_level_rewards(
            guild=guild,
            user_id=self.target_id,
            previous_level=current.level,
            new_level=updated.level,
        )

        self.cog.log_admin_action(
            action=f"QUITAR {amount} XP",
            guild_id=guild.id,
            admin_id=interaction.user.id,
            target_id=self.target_id,
            before=current,
            after=updated,
        )

        await interaction.response.send_message(
            embed=self.cog.create_admin_embed(
                guild=guild,
                target_id=self.target_id,
                action_message=(
                    f"Ã¢Å“â€¦ Se quitaron **{amount:,} XP**."
                ),
            ),
            view=AdminLevelView(
                cog=self.cog,
                admin_id=interaction.user.id,
                guild_id=guild.id,
                target_id=self.target_id,
            ),
            ephemeral=True,
        )


class ResetConfirmationView(discord.ui.View):
    """Confirmation controls for a level reset."""

    def __init__(
        self,
        cog: "Niveles",
        admin_id: int,
        guild_id: int,
        target_id: int,
        parent_view: AdminLevelView,
    ) -> None:
        super().__init__(timeout=60)

        self.cog = cog
        self.admin_id = admin_id
        self.guild_id = guild_id
        self.target_id = target_id
        self.parent_view = parent_view

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """Only the original administrator can confirm."""
        if interaction.user.id == self.admin_id:
            return True

        await interaction.response.send_message(
            "Ã¢ÂÅ’ No puedes utilizar esta confirmaciÃƒÂ³n.",
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Confirmar reset",
        emoji="Ã°Å¸â€Â´",
        style=discord.ButtonStyle.danger,
    )
    async def confirm_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Reset the user's level."""
        current = self.cog.level_service.repository.get_user(
            self.guild_id,
            self.target_id,
        )

        updated = self.cog.level_service.reset_user(
            guild_id=self.guild_id,
            user_id=self.target_id,
            current_time=time.time(),
        )

        await self.cog._remove_all_level_rewards(
            guild=interaction.guild,
            user_id=self.target_id,
        )

        self.cog.log_admin_action(
            action="RESET",
            guild_id=self.guild_id,
            admin_id=self.admin_id,
            target_id=self.target_id,
            before=current,
            after=updated,
        )

        await interaction.response.edit_message(
            embed=self.cog.create_admin_embed(
                guild=interaction.guild,
                target_id=self.target_id,
                action_message=(
                    "Ã°Å¸â€â€ž El nivel, la experiencia y las "
                    "recompensas fueron completamente reseteados."
                ),
            ),
            view=self.parent_view,
        )

        self.stop()

    @discord.ui.button(
        label="Cancelar",
        emoji="Ã¢ÂÅ’",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Cancel the reset."""
        await interaction.response.edit_message(
            content="Ã¢ÂÅ’ Reset cancelado.",
            embed=None,
            view=None,
        )

        self.stop()


class LevelChannelConfigView(discord.ui.View):
    """Interactive configuration for the level-up announcement channel."""

    def __init__(
        self,
        cog: "Niveles",
        admin_id: int,
        guild_id: int,
    ) -> None:
        super().__init__(timeout=300)

        self.cog = cog
        self.admin_id = admin_id
        self.guild_id = guild_id

        self.channel_select = discord.ui.ChannelSelect(
            placeholder="Selecciona el canal de mensajes de niveles...",
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news,
            ],
            min_values=1,
            max_values=1,
        )

        self.channel_select.callback = self.channel_selected
        self.add_item(self.channel_select)

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """Only the administrator who opened the panel can use it."""
        if interaction.user.id == self.admin_id:
            return True

        await interaction.response.send_message(
            "❌ Solo el administrador que abrió esta configuración puede utilizarla.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="Quitar canal",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
        row=1,
    )
    async def clear_channel_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Remove the configured channel."""
        self.cog.level_service.repository.set_level_channel(
            self.guild_id,
            None,
        )

        await interaction.response.edit_message(
            content=(
                "✅ Canal de niveles eliminado.\n\n"
                "Los mensajes de subida de nivel volverán a "
                "mostrarse en el canal donde ocurrió la subida."
            ),
            embed=None,
            view=None,
        )

        self.stop()

    async def channel_selected(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Save the selected level-up channel."""
        if not self.channel_select.values:
            await interaction.response.send_message(
                "❌ No se seleccionó ningún canal.",
                ephemeral=True,
            )
            return

        selected = self.channel_select.values[0]
        channel_id = getattr(selected, "id", None)

        if channel_id is None:
            await interaction.response.send_message(
                "❌ No se pudo identificar el canal seleccionado.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)

        if channel is None:
            await interaction.response.send_message(
                "❌ No se encontró el canal seleccionado.",
                ephemeral=True,
            )
            return

        self.cog.level_service.repository.set_level_channel(
            self.guild_id,
            channel.id,
        )

        await interaction.response.edit_message(
            content=(
                "✅ Canal de niveles configurado correctamente.\n\n"
                "Los mensajes de subida de nivel se enviarán en "
                f"{channel.mention}."
            ),
            embed=None,
            view=None,
        )

        self.stop()

class Niveles(commands.Cog):
    """Handle XP, levels, leaderboards and administration."""

    niveles_group = app_commands.Group(
        name="niveles",
        description="Activa o desactiva el sistema automÃƒÂ¡tico de niveles.",
    )

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot
        self.level_service = LevelService()
        self.reward_service = RewardService()

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ) -> None:
        """Award XP when a valid user sends a message."""
        if message.author.bot:
            return

        if message.guild is None:
            return

        if not self.level_service.is_enabled(
            message.guild.id
        ):
            return

        current = self.level_service.repository.get_user(
            guild_id=message.guild.id,
            user_id=message.author.id,
        )

        xp_amount = random.randint(
            MIN_XP_PER_MESSAGE,
            MAX_XP_PER_MESSAGE,
        )

        result = self.level_service.register_message(
            guild_id=message.guild.id,
            user_id=message.author.id,
            xp_amount=xp_amount,
            current_time=time.time(),
        )

        if result is None:
            return

        user_data, leveled_up = result

        if not leveled_up:
            return

        await self._sync_level_rewards(
            guild=message.guild,
            user_id=message.author.id,
            previous_level=current.level,
            new_level=user_data.level,
        )

        LOGGER.info(
            "User %s reached level %s in guild %s.",
            message.author.id,
            user_data.level,
            message.guild.id,
        )

        await self._announce_level_up(
            message=message,
            level=user_data.level,
        )

    @niveles_group.command(
        name="activar",
        description="Activa la ganancia automÃƒÂ¡tica de XP por mensajes.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def niveles_activar(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Enable automatic leveling."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ Este comando solamente puede utilizarse "
                "dentro de un servidor.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id

        if self.level_service.is_enabled(guild_id):
            await interaction.response.send_message(
                "Ã¢â€žÂ¹Ã¯Â¸Â El sistema de niveles ya estÃƒÂ¡ **activo**.",
                ephemeral=True,
            )
            return

        self.level_service.enable(guild_id)

        LOGGER.info(
            (
                "LEVEL SYSTEM | Activado | "
                "Servidor=%s | Admin=%s"
            ),
            guild_id,
            interaction.user.id,
        )

        await interaction.response.send_message(
            "Ã¢Å“â€¦ El sistema de niveles ha sido **activado**.\n\n"
            "Los mensajes volverÃƒÂ¡n a otorgar XP automÃƒÂ¡ticamente.",
            ephemeral=True,
        )

    @niveles_group.command(
        name="desactivar",
        description="Desactiva la ganancia automÃƒÂ¡tica de XP por mensajes.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def niveles_desactivar(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Disable automatic leveling."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ Este comando solamente puede utilizarse "
                "dentro de un servidor.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id

        if not self.level_service.is_enabled(guild_id):
            await interaction.response.send_message(
                "Ã¢â€žÂ¹Ã¯Â¸Â El sistema de niveles ya estÃƒÂ¡ **desactivado**.",
                ephemeral=True,
            )
            return

        self.level_service.disable(guild_id)

        LOGGER.info(
            (
                "LEVEL SYSTEM | Desactivado | "
                "Servidor=%s | Admin=%s"
            ),
            guild_id,
            interaction.user.id,
        )

        await interaction.response.send_message(
            "Ã¢ÂÂ¸Ã¯Â¸Â El sistema de niveles ha sido **desactivado**.\n\n"
            "Los mensajes ya no otorgarÃƒÂ¡n XP automÃƒÂ¡ticamente.\n"
            "Los datos existentes, niveles y recompensas "
            "se conservarÃƒÂ¡n.",
            ephemeral=True,
        )

    @app_commands.command(
        name="niveles_configurar_canal",
        description=(
            "Configura el canal donde se muestran los mensajes de niveles."
        ),
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def niveles_configurar_canal(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Configure the channel used for level-up announcements."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ Este comando solamente puede utilizarse "
                "dentro de un servidor.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id

        current_channel_id = (
            self.level_service.repository.get_level_channel(
                guild_id
            )
        )

        current_channel = None

        if current_channel_id is not None:
            current_channel = interaction.guild.get_channel(
                current_channel_id
            )

        if current_channel is not None:
            current_text = (
                f"Actualmente: {current_channel.mention}\n\n"
                "Selecciona un nuevo canal para cambiarlo."
            )
        else:
            current_text = (
                "Actualmente: **sin canal configurado**.\n\n"
                "Selecciona un canal para configurarlo."
            )

        embed = discord.Embed(
            title="Ã°Å¸â€œÂ¢ Canal de niveles",
            description=current_text,
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="Ã‚Â¿DÃƒÂ³nde aparecerÃƒÂ¡n los mensajes?",
            value=(
                "Cuando un usuario suba de nivel, Odinus enviarÃƒÂ¡ "
                "el anuncio en el canal seleccionado."
            ),
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            view=LevelChannelConfigView(
                cog=self,
                admin_id=interaction.user.id,
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    @niveles_activar.error
    @niveles_desactivar.error
    @niveles_configurar_canal.error
    async def niveles_config_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle level configuration permission errors."""
        if isinstance(
            error,
            app_commands.MissingPermissions,
        ):
            await interaction.response.send_message(
                "Ã¢ÂÅ’ Necesitas tener el permiso de "
                "**Administrador** para utilizar este comando.",
                ephemeral=True,
            )
            return

        LOGGER.exception(
            "Error in /niveles configuration command.",
            exc_info=error,
        )

        if interaction.response.is_done():
            await interaction.followup.send(
                "Ã¢ÂÅ’ OcurriÃƒÂ³ un error al modificar el sistema de niveles.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ OcurriÃƒÂ³ un error al modificar el sistema de niveles.",
                ephemeral=True,
            )

    @app_commands.command(
        name="nivel",
        description="Consulta tu nivel y experiencia actual.",
    )
    @app_commands.describe(
        usuario="Usuario cuyo nivel quieres consultar.",
    )
    async def nivel(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member | None = None,
    ) -> None:
        """Display the current level information."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ Este comando solamente puede utilizarse "
                "dentro de un servidor.",
                ephemeral=True,
            )
            return

        target = usuario or interaction.user

        embed = self.create_level_embed(
            guild=interaction.guild,
            target_id=target.id,
        )

        view = self.create_level_view(
            owner_id=interaction.user.id,
            guild_id=interaction.guild.id,
            target_id=target.id,
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
        )

    @app_commands.command(
        name="nivel_administrar",
        description="Administra el nivel y XP de un usuario.",
    )
    @app_commands.describe(
        usuario="Usuario que quieres administrar.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def nivel_administrar(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
    ) -> None:
        """Open the administrative level panel."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ Este comando solamente puede utilizarse "
                "dentro de un servidor.",
                ephemeral=True,
            )
            return

        embed = self.create_admin_embed(
            guild=interaction.guild,
            target_id=usuario.id,
        )

        view = AdminLevelView(
            cog=self,
            admin_id=interaction.user.id,
            guild_id=interaction.guild.id,
            target_id=usuario.id,
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True,
        )

    @nivel_administrar.error
    async def nivel_administrar_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle administration permission errors."""
        if isinstance(
            error,
            app_commands.MissingPermissions,
        ):
            await interaction.response.send_message(
                "Ã¢ÂÅ’ Necesitas tener el permiso de "
                "**Administrador** para utilizar este comando.",
                ephemeral=True,
            )
            return

        LOGGER.exception(
            "Error in /nivel_administrar.",
            exc_info=error,
        )

        if interaction.response.is_done():
            await interaction.followup.send(
                "Ã¢ÂÅ’ OcurriÃƒÂ³ un error al abrir el panel administrativo.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Ã¢ÂÅ’ OcurriÃƒÂ³ un error al abrir el panel administrativo.",
                ephemeral=True,
            )

    def create_level_view(
        self,
        owner_id: int,
        guild_id: int,
        target_id: int,
    ) -> LevelView:
        """Create the level profile view."""
        return LevelView(
            cog=self,
            owner_id=owner_id,
            guild_id=guild_id,
            target_id=target_id,
        )

    def create_level_embed(
        self,
        guild: discord.Guild,
        target_id: int,
    ) -> discord.Embed:
        """Create the user's level embed."""
        target = guild.get_member(target_id)

        if target is None:
            display_name = f"Usuario {target_id}"
            avatar_url = None
        else:
            display_name = target.display_name
            avatar_url = target.display_avatar.url

        user_data = self.level_service.repository.get_user(
            guild_id=guild.id,
            user_id=target_id,
        )

        xp_into_level, xp_required = (
            self.level_service.xp_progress(
                user_data.total_xp,
            )
        )

        if user_data.level >= MAX_LEVEL:
            progress_percentage = 100
            xp_remaining = 0
            progress_bar = "Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†"
        else:
            if xp_required > 0:
                progress_percentage = int(
                    (
                        xp_into_level
                        / xp_required
                    ) * 100
                )
            else:
                progress_percentage = 0

            progress_percentage = min(
                100,
                max(0, progress_percentage),
            )

            xp_remaining = max(
                0,
                xp_required - xp_into_level,
            )

            progress_bar = self._create_progress_bar(
                percentage=progress_percentage,
            )

        embed = discord.Embed(
            title="Ã°Å¸â€œÅ  Nivel de Odinus",
            description=f"**{display_name}**",
            color=discord.Color.blurple(),
        )

        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.add_field(
            name="Ã¢Â­Â Nivel",
            value=f"**{user_data.level}**",
            inline=True,
        )

        embed.add_field(
            name="Ã¢Å“Â¨ XP total",
            value=f"**{user_data.total_xp:,} XP**",
            inline=True,
        )

        if user_data.level >= MAX_LEVEL:
            progress_text = (
                f"{progress_bar}\n"
                "**Nivel mÃƒÂ¡ximo alcanzado**"
            )
        else:
            progress_text = (
                f"{progress_bar}\n"
                f"**{xp_into_level:,} / "
                f"{xp_required:,} XP** "
                f"({progress_percentage}%)"
            )

        embed.add_field(
            name="Ã°Å¸â€œË† Progreso",
            value=progress_text,
            inline=False,
        )

        if user_data.level >= MAX_LEVEL:
            next_level_text = "Ã°Å¸Ââ€  Nivel mÃƒÂ¡ximo"
            remaining_text = "0 XP"
        else:
            next_level_text = (
                f"**Nivel {user_data.level + 1}**"
            )
            remaining_text = f"**{xp_remaining:,} XP**"

        embed.add_field(
            name="Ã°Å¸Å½Â¯ Siguiente nivel",
            value=next_level_text,
            inline=True,
        )

        embed.add_field(
            name="Ã¢Å¡Â¡ XP restante",
            value=remaining_text,
            inline=True,
        )

        embed.set_footer(
            text="Odinus Levels Ã¢â‚¬Â¢ v1.4",
        )

        return embed

    def create_admin_embed(
        self,
        guild: discord.Guild,
        target_id: int,
        action_message: str | None = None,
    ) -> discord.Embed:
        """Create the administrative panel embed."""
        target = guild.get_member(target_id)

        if target is None:
            display_name = f"Usuario {target_id}"
            avatar_url = None
        else:
            display_name = target.display_name
            avatar_url = target.display_avatar.url

        user_data = self.level_service.repository.get_user(
            guild_id=guild.id,
            user_id=target_id,
        )

        embed = discord.Embed(
            title="Ã¢Å¡â„¢Ã¯Â¸Â AdministraciÃƒÂ³n de niveles",
            description=(
                f"Usuario seleccionado: "
                f"**{display_name}**\n"
                f"<@{target_id}>"
            ),
            color=discord.Color.dark_gold(),
        )

        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.add_field(
            name="Ã¢Â­Â Nivel actual",
            value=f"**{user_data.level}**",
            inline=True,
        )

        embed.add_field(
            name="Ã¢Å“Â¨ XP total",
            value=f"**{user_data.total_xp:,} XP**",
            inline=True,
        )

        if action_message:
            embed.add_field(
                name="Resultado",
                value=action_message,
                inline=False,
            )

        embed.set_footer(
            text="Odinus Levels Ã¢â‚¬Â¢ AdministraciÃƒÂ³n v1.4",
        )

        return embed

    def create_ranking_embed(
        self,
        guild: discord.Guild,
        page: int,
    ) -> discord.Embed:
        """Create a paginated leaderboard embed."""
        total_users = self.level_service.repository.count_users(
            guild.id
        )

        total_pages = max(
            1,
            (
                total_users + LEADERBOARD_PAGE_SIZE - 1
            ) // LEADERBOARD_PAGE_SIZE,
        )

        page = min(
            max(page, 0),
            total_pages - 1,
        )

        offset = page * LEADERBOARD_PAGE_SIZE

        users = self.level_service.repository.get_leaderboard(
            guild_id=guild.id,
            limit=LEADERBOARD_PAGE_SIZE,
            offset=offset,
        )

        embed = discord.Embed(
            title="Ã°Å¸Ââ€  Ranking de niveles",
            description=(
                f"Los usuarios con mÃƒÂ¡s experiencia de "
                f"**{guild.name}**."
            ),
            color=discord.Color.gold(),
        )

        if not users:
            embed.description = (
                "TodavÃƒÂ­a no hay usuarios con experiencia "
                "registrada en este servidor."
            )

            embed.set_footer(
                text="Odinus Levels Ã¢â‚¬Â¢ PÃƒÂ¡gina 1/1",
            )

            return embed

        lines: list[str] = []

        for index, user_data in enumerate(users):
            rank = offset + index + 1

            member = guild.get_member(
                user_data.user_id
            )

            if member is not None:
                name = member.display_name
                mention = member.mention
            else:
                name = f"Usuario {user_data.user_id}"
                mention = f"<@{user_data.user_id}>"

            if rank == 1:
                position = "Ã°Å¸Â¥â€¡"
            elif rank == 2:
                position = "Ã°Å¸Â¥Ë†"
            elif rank == 3:
                position = "Ã°Å¸Â¥â€°"
            else:
                position = f"**#{rank}**"

            lines.append(
                f"{position} {mention} Ã¢â‚¬â€ **{name}**\n"
                f"   Ã¢Â­Â Nivel **{user_data.level}** Ã¢â‚¬Â¢ "
                f"Ã¢Å“Â¨ **{user_data.total_xp:,} XP**"
            )

        embed.add_field(
            name="ClasificaciÃƒÂ³n",
            value="\n\n".join(lines),
            inline=False,
        )

        embed.set_footer(
            text=(
                f"Odinus Levels Ã¢â‚¬Â¢ PÃƒÂ¡gina "
                f"{page + 1}/{total_pages} Ã¢â‚¬Â¢ "
                f"{total_users} usuarios"
            ),
        )

        return embed

    def log_admin_action(
        self,
        action: str,
        guild_id: int,
        admin_id: int,
        target_id: int,
        before,
        after,
    ) -> None:
        """Log an administrative level modification."""
        LOGGER.info(
            (
                "LEVEL ADMIN | AcciÃƒÂ³n=%s | "
                "Servidor=%s | Admin=%s | Usuario=%s | "
                "Antes=(Nivel %s, XP %s) | "
                "DespuÃƒÂ©s=(Nivel %s, XP %s)"
            ),
            action,
            guild_id,
            admin_id,
            target_id,
            before.level,
            before.total_xp,
            after.level,
            after.total_xp,
        )

    async def _sync_level_rewards(
        self,
        guild: discord.Guild | None,
        user_id: int,
        previous_level: int,
        new_level: int,
    ) -> None:
        """
        Synchronize Odinus reward roles after a level change.

        When leveling up, rewards between the old and new levels
        are assigned.

        When leveling down, reward roles above the new level are
        removed, while rewards still valid for the current level
        remain.
        """
        if guild is None:
            return

        if previous_level == new_level:
            return

        member = guild.get_member(user_id)

        if member is None:
            LOGGER.warning(
                (
                    "Could not synchronize level rewards because "
                    "user %s was not found in guild %s."
                ),
                user_id,
                guild.id,
            )
            return

        if new_level > previous_level:
            rewards = self.reward_service.get_rewards_between_levels(
                guild_id=guild.id,
                minimum_level=previous_level + 1,
                maximum_level=new_level,
            )

            await self._assign_level_rewards(
                member=member,
                rewards=rewards,
            )

            return

        await self._remove_rewards_above_level(
            member=member,
            current_level=new_level,
        )

    async def _assign_level_rewards(
        self,
        member: discord.Member,
        rewards: list[LevelReward],
    ) -> None:
        """Assign configured reward roles to a member."""
        for reward in rewards:
            role = member.guild.get_role(
                reward.role_id,
            )

            if role is None:
                LOGGER.warning(
                    (
                        "Reward role does not exist: "
                        "guild=%s level=%s role_id=%s."
                    ),
                    member.guild.id,
                    reward.level,
                    reward.role_id,
                )
                continue

            if role.is_default() or role.managed:
                LOGGER.warning(
                    (
                        "Skipping invalid reward role: "
                        "guild=%s level=%s role_id=%s."
                    ),
                    member.guild.id,
                    reward.level,
                    reward.role_id,
                )
                continue

            if role in member.roles:
                LOGGER.info(
                    (
                        "User already has reward role: "
                        "guild=%s user=%s level=%s role_id=%s."
                    ),
                    member.guild.id,
                    member.id,
                    reward.level,
                    role.id,
                )
                continue

            if not role.is_assignable():
                LOGGER.warning(
                    (
                        "Reward role cannot be assigned by Odinus: "
                        "guild=%s level=%s role=%s role_id=%s."
                    ),
                    member.guild.id,
                    reward.level,
                    role.name,
                    role.id,
                )
                continue

            try:
                await member.add_roles(
                    role,
                    reason=(
                        f"Odinus: recompensa por alcanzar "
                        f"nivel {reward.level}"
                    ),
                )

                LOGGER.info(
                    (
                        "Reward role assigned: "
                        "guild=%s user=%s level=%s role_id=%s."
                    ),
                    member.guild.id,
                    member.id,
                    reward.level,
                    role.id,
                )

            except discord.Forbidden:
                LOGGER.warning(
                    (
                        "Odinus lacks permission to assign reward role: "
                        "guild=%s user=%s level=%s role_id=%s."
                    ),
                    member.guild.id,
                    member.id,
                    reward.level,
                    role.id,
                )

            except discord.HTTPException:
                LOGGER.exception(
                    (
                        "Discord API error while assigning reward role: "
                        "guild=%s user=%s level=%s role_id=%s."
                    ),
                    member.guild.id,
                    member.id,
                    reward.level,
                    role.id,
                )

    async def _remove_rewards_above_level(
        self,
        member: discord.Member,
        current_level: int,
    ) -> None:
        """
        Remove Odinus reward roles that are above the current level.

        A role is preserved if another configured reward at or below
        the current level uses the same Discord role.
        """
        rewards_above = self.reward_service.get_rewards_above_level(
            guild_id=member.guild.id,
            level=current_level,
        )

        if not rewards_above:
            return

        rewards_at_or_below = (
            self.reward_service.get_rewards_between_levels(
                guild_id=member.guild.id,
                minimum_level=1,
                maximum_level=current_level,
            )
        )

        protected_role_ids = {
            reward.role_id
            for reward in rewards_at_or_below
        }

        role_ids_to_remove = {
            reward.role_id
            for reward in rewards_above
            if reward.role_id not in protected_role_ids
        }

        for role_id in role_ids_to_remove:
            role = member.guild.get_role(role_id)

            if role is None:
                LOGGER.info(
                    (
                        "Reward role already deleted from Discord: "
                        "guild=%s role_id=%s."
                    ),
                    member.guild.id,
                    role_id,
                )
                continue

            if role.is_default() or role.managed:
                continue

            if role not in member.roles:
                continue

            if not role.is_assignable():
                LOGGER.warning(
                    (
                        "Odinus cannot remove reward role: "
                        "guild=%s user=%s role=%s role_id=%s."
                    ),
                    member.guild.id,
                    member.id,
                    role.name,
                    role.id,
                )
                continue

            try:
                await member.remove_roles(
                    role,
                    reason=(
                        f"Odinus: usuario bajÃƒÂ³ al nivel {current_level}"
                    ),
                )

                LOGGER.info(
                    (
                        "Reward role removed: "
                        "guild=%s user=%s current_level=%s role_id=%s."
                    ),
                    member.guild.id,
                    member.id,
                    current_level,
                    role.id,
                )

            except discord.Forbidden:
                LOGGER.warning(
                    (
                        "Odinus lacks permission to remove reward role: "
                        "guild=%s user=%s role_id=%s."
                    ),
                    member.guild.id,
                    member.id,
                    role_id,
                )

            except discord.HTTPException:
                LOGGER.exception(
                    (
                        "Discord API error while removing reward role: "
                        "guild=%s user=%s role_id=%s."
                    ),
                    member.guild.id,
                    member.id,
                    role_id,
                )

    async def _remove_all_level_rewards(
        self,
        guild: discord.Guild | None,
        user_id: int,
    ) -> None:
        """Remove every reward role managed by Odinus."""
        if guild is None:
            return

        member = guild.get_member(user_id)

        if member is None:
            LOGGER.warning(
                (
                    "Could not remove level rewards because "
                    "user %s was not found in guild %s."
                ),
                user_id,
                guild.id,
            )
            return

        managed_role_ids = (
            self.reward_service.get_managed_role_ids(
                guild.id,
            )
        )

        if not managed_role_ids:
            return

        for role_id in managed_role_ids:
            role = guild.get_role(role_id)

            if role is None:
                LOGGER.info(
                    (
                        "Managed reward role no longer exists: "
                        "guild=%s role_id=%s."
                    ),
                    guild.id,
                    role_id,
                )
                continue

            if role.is_default() or role.managed:
                continue

            if role not in member.roles:
                continue

            if not role.is_assignable():
                LOGGER.warning(
                    (
                        "Odinus cannot remove reward role during reset: "
                        "guild=%s user=%s role_id=%s."
                    ),
                    guild.id,
                    user_id,
                    role_id,
                )
                continue

            try:
                await member.remove_roles(
                    role,
                    reason="Odinus: reset completo de niveles",
                )

                LOGGER.info(
                    (
                        "Reward role removed during reset: "
                        "guild=%s user=%s role_id=%s."
                    ),
                    guild.id,
                    user_id,
                    role_id,
                )

            except discord.Forbidden:
                LOGGER.warning(
                    (
                        "Odinus lacks permission to remove reward role "
                        "during reset: guild=%s user=%s role_id=%s."
                    ),
                    guild.id,
                    user_id,
                    role_id,
                )

            except discord.HTTPException:
                LOGGER.exception(
                    (
                        "Discord API error while removing reward role "
                        "during reset: guild=%s user=%s role_id=%s."
                    ),
                    guild.id,
                    user_id,
                    role_id,
                )

    @staticmethod
    def _create_progress_bar(
        percentage: int,
        length: int = 20,
    ) -> str:
        """Create a text progress bar."""
        filled = round(
            (percentage / 100) * length
        )

        filled = min(
            length,
            max(0, filled),
        )

        return (
            "Ã¢â€“Ë†" * filled
            + "Ã¢â€“â€˜" * (length - filled)
        )

    async def _announce_level_up(
        self,
        message: discord.Message,
        level: int,
    ) -> None:
        """Announce a level-up in the configured channel."""
        channel_id = (
            self.level_service.repository.get_level_channel(
                message.guild.id
            )
        )

        target_channel = None

        if channel_id is not None:
            configured_channel = message.guild.get_channel(
                channel_id
            )

            if isinstance(
                configured_channel,
                discord.TextChannel,
            ):
                target_channel = configured_channel
            else:
                LOGGER.warning(
                    (
                        "Configured level channel is unavailable: "
                        "guild=%s channel_id=%s."
                    ),
                    message.guild.id,
                    channel_id,
                )

        if target_channel is None:
            target_channel = message.channel

        try:
            await target_channel.send(
                f"Ã°Å¸Å½â€° Ã‚Â¡{message.author.mention} ha alcanzado "
                f"el **nivel {level}**!"
            )
        except discord.Forbidden:
            LOGGER.warning(
                (
                    "Could not announce level-up for user %s "
                    "in channel %s."
                ),
                message.author.id,
                target_channel.id,
            )
        except discord.HTTPException:
            LOGGER.exception(
                (
                    "Discord API error while announcing level-up "
                    "for user %s in channel %s."
                ),
                message.author.id,
                target_channel.id,
            )


async def setup(
    bot: commands.Bot,
) -> None:
    """Load the leveling Cog."""
    await bot.add_cog(Niveles(bot))