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
        emoji="🏆",
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
                "❌ Solo la persona que ejecutó este comando "
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
            "❌ Solo la persona que ejecutó este comando "
            "puede utilizar estos botones.",
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Anterior",
        emoji="◀️",
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
        emoji="👤",
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
        emoji="▶️",
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
            "❌ Solo el administrador que abrió este panel "
            "puede utilizarlo.",
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Dar XP",
        emoji="➕",
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
        emoji="➖",
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
        emoji="⬆️",
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
                "🏆 El usuario ya se encuentra en el nivel máximo.",
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
                    f"✅ Nivel aumentado: "
                    f"**{current.level} → {updated.level}**"
                ),
            ),
            view=self,
        )

    @discord.ui.button(
        label="Bajar nivel",
        emoji="⬇️",
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
                "❌ El usuario ya se encuentra en el nivel 0.",
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
                    f"✅ Nivel reducido: "
                    f"**{current.level} → {updated.level}**"
                ),
            ),
            view=self,
        )

    @discord.ui.button(
        label="Resetear",
        emoji="🔄",
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
                title="⚠️ Confirmar reset",
                description=(
                    f"¿Seguro que quieres resetear completamente "
                    f"a <@{self.target_id}>?\n\n"
                    "Esto establecerá:\n"
                    "• Nivel: **0**\n"
                    "• XP: **0**\n"
                    "• Recompensas de nivel: **se retirarán**\n\n"
                    "Esta acción no puede deshacerse automáticamente."
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


class AddXPModal(discord.ui.Modal, title="➕ Dar experiencia"):
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
                "❌ Debes introducir una cantidad numérica válida.",
                ephemeral=True,
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "❌ La cantidad debe ser mayor que 0.",
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
                    f"✅ Se otorgaron **{amount:,} XP**."
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


class RemoveXPModal(discord.ui.Modal, title="➖ Quitar experiencia"):
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
                "❌ Debes introducir una cantidad numérica válida.",
                ephemeral=True,
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "❌ La cantidad debe ser mayor que 0.",
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
                    f"✅ Se quitaron **{amount:,} XP**."
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
            "❌ No puedes utilizar esta confirmación.",
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Confirmar reset",
        emoji="🔴",
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
                    "🔄 El nivel, la experiencia y las "
                    "recompensas fueron completamente reseteados."
                ),
            ),
            view=self.parent_view,
        )

        self.stop()

    @discord.ui.button(
        label="Cancelar",
        emoji="❌",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Cancel the reset."""
        await interaction.response.edit_message(
            content="❌ Reset cancelado.",
            embed=None,
            view=None,
        )

        self.stop()


class Niveles(commands.Cog):
    """Handle XP, levels, leaderboards and administration."""

    niveles_group = app_commands.Group(
        name="niveles",
        description="Activa o desactiva el sistema automático de niveles.",
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

        # Do not award automatic XP while leveling is disabled.
        if not self.level_service.is_enabled(
            message.guild.id
        ):
            return

        # Capture the real level before processing the message.
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
        description="Activa la ganancia automática de XP por mensajes.",
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
                "❌ Este comando solamente puede utilizarse "
                "dentro de un servidor.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id

        if self.level_service.is_enabled(guild_id):
            await interaction.response.send_message(
                "ℹ️ El sistema de niveles ya está **activo**.",
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
            "✅ El sistema de niveles ha sido **activado**.\n\n"
            "Los mensajes volverán a otorgar XP automáticamente.",
            ephemeral=True,
        )

    @niveles_group.command(
        name="desactivar",
        description="Desactiva la ganancia automática de XP por mensajes.",
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
                "❌ Este comando solamente puede utilizarse "
                "dentro de un servidor.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id

        if not self.level_service.is_enabled(guild_id):
            await interaction.response.send_message(
                "ℹ️ El sistema de niveles ya está **desactivado**.",
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
            "⏸️ El sistema de niveles ha sido **desactivado**.\n\n"
            "Los mensajes ya no otorgarán XP automáticamente.\n"
            "Los datos existentes, niveles y recompensas "
            "se conservarán.",
            ephemeral=True,
        )

    @niveles_activar.error
    @niveles_desactivar.error
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
                "❌ Necesitas tener el permiso de "
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
                "❌ Ocurrió un error al modificar el sistema de niveles.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "❌ Ocurrió un error al modificar el sistema de niveles.",
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
                "❌ Este comando solamente puede utilizarse "
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
                "❌ Este comando solamente puede utilizarse "
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
                "❌ Necesitas tener el permiso de "
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
                "❌ Ocurrió un error al abrir el panel administrativo.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "❌ Ocurrió un error al abrir el panel administrativo.",
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
            progress_bar = "████████████████████"
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
            title="📊 Nivel de Odinus",
            description=f"**{display_name}**",
            color=discord.Color.blurple(),
        )

        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.add_field(
            name="⭐ Nivel",
            value=f"**{user_data.level}**",
            inline=True,
        )

        embed.add_field(
            name="✨ XP total",
            value=(
                f"**{user_data.total_xp:,} XP**"
            ),
            inline=True,
        )

        if user_data.level >= MAX_LEVEL:
            progress_text = (
                f"{progress_bar}\n"
                "**Nivel máximo alcanzado**"
            )
        else:
            progress_text = (
                f"{progress_bar}\n"
                f"**{xp_into_level:,} / "
                f"{xp_required:,} XP** "
                f"({progress_percentage}%)"
            )

        embed.add_field(
            name="📈 Progreso",
            value=progress_text,
            inline=False,
        )

        if user_data.level >= MAX_LEVEL:
            next_level_text = "🏆 Nivel máximo"
            remaining_text = "0 XP"
        else:
            next_level_text = (
                f"**Nivel {user_data.level + 1}**"
            )
            remaining_text = (
                f"**{xp_remaining:,} XP**"
            )

        embed.add_field(
            name="🎯 Siguiente nivel",
            value=next_level_text,
            inline=True,
        )

        embed.add_field(
            name="⚡ XP restante",
            value=remaining_text,
            inline=True,
        )

        embed.set_footer(
            text="Odinus Levels • v1.4",
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
            title="⚙️ Administración de niveles",
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
            name="⭐ Nivel actual",
            value=f"**{user_data.level}**",
            inline=True,
        )

        embed.add_field(
            name="✨ XP total",
            value=(
                f"**{user_data.total_xp:,} XP**"
            ),
            inline=True,
        )

        if action_message:
            embed.add_field(
                name="Resultado",
                value=action_message,
                inline=False,
            )

        embed.set_footer(
            text=(
                "Odinus Levels • Administración v1.4"
            ),
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
            title="🏆 Ranking de niveles",
            description=(
                f"Los usuarios con más experiencia de "
                f"**{guild.name}**."
            ),
            color=discord.Color.gold(),
        )

        if not users:
            embed.description = (
                "Todavía no hay usuarios con experiencia "
                "registrada en este servidor."
            )

            embed.set_footer(
                text="Odinus Levels • Página 1/1",
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
                name = (
                    f"Usuario {user_data.user_id}"
                )
                mention = (
                    f"<@{user_data.user_id}>"
                )

            if rank == 1:
                position = "🥇"
            elif rank == 2:
                position = "🥈"
            elif rank == 3:
                position = "🥉"
            else:
                position = f"**#{rank}**"

            lines.append(
                f"{position} {mention} — **{name}**\n"
                f"   ⭐ Nivel **{user_data.level}** • "
                f"✨ **{user_data.total_xp:,} XP**"
            )

        embed.add_field(
            name="Clasificación",
            value="\n\n".join(lines),
            inline=False,
        )

        embed.set_footer(
            text=(
                f"Odinus Levels • Página "
                f"{page + 1}/{total_pages} • "
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
                "LEVEL ADMIN | Acción=%s | "
                "Servidor=%s | Admin=%s | Usuario=%s | "
                "Antes=(Nivel %s, XP %s) | "
                "Después=(Nivel %s, XP %s)"
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

        rewards_at_or_below = self.reward_service.get_rewards_between_levels(
            guild_id=member.guild.id,
            minimum_level=1,
            maximum_level=current_level,
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
                        f"Odinus: usuario bajó al nivel {current_level}"
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
            "█" * filled
            + "░" * (length - filled)
        )

    async def _announce_level_up(
        self,
        message: discord.Message,
        level: int,
    ) -> None:
        """Announce a level-up in the channel where it happened."""
        try:
            await message.channel.send(
                f"🎉 ¡{message.author.mention} ha alcanzado "
                f"el **nivel {level}**!"
            )
        except discord.Forbidden:
            LOGGER.warning(
                "Could not announce level-up for user %s in channel %s.",
                message.author.id,
                message.channel.id,
            )


async def setup(
    bot: commands.Bot,
) -> None:
    """Load the leveling Cog."""
    await bot.add_cog(Niveles(bot))