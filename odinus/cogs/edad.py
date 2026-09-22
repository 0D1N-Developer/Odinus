"""Age self-role system for Discord servers."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from odinus.services.edad import AgeRepository

LOGGER = logging.getLogger(__name__)


AGE_ROLES = (
    ("18plus", "🔞", "+18"),
    ("under18", "🔒", "-18"),
)


def age_role_name(emoji: str, name: str) -> str:
    """Build the standard age role name."""
    return f"『{emoji}』{name}"


class AgeButton(discord.ui.Button):
    """Button that assigns an age role."""

    def __init__(
        self,
        age_code: str,
        emoji: str,
        age_name: str,
    ) -> None:
        super().__init__(
            label=age_name,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"odinus:age:{age_code}",
        )

        self.age_code = age_code
        self.age_emoji = emoji
        self.age_name = age_name

    async def callback(self, interaction: discord.Interaction) -> None:
        """Assign the selected age role and remove the other one."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este botón solo puede utilizarse dentro de un servidor.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "No pude obtener tu información de miembro.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        member = interaction.user

        selected_role_name = age_role_name(
            self.age_emoji,
            self.age_name,
        )

        selected_role = discord.utils.get(
            guild.roles,
            name=selected_role_name,
        )

        if selected_role is None:
            await interaction.response.send_message(
                "El rol de edad no existe actualmente. "
                "Pide a un administrador que vuelva a configurar "
                "los autoroles.",
                ephemeral=True,
            )
            return

        age_role_names = {
            age_role_name(emoji, name)
            for _, emoji, name in AGE_ROLES
        }

        roles_to_remove = [
            role
            for role in member.roles
            if role.name in age_role_names
            and role != selected_role
        ]

        try:
            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove,
                    reason="Cambio de rol de edad mediante Odinus.",
                )

            if selected_role not in member.roles:
                await member.add_roles(
                    selected_role,
                    reason="Selección de rol de edad mediante Odinus.",
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                "No puedo administrar los roles de edad. "
                "Verifica que mi rol esté por encima de los roles "
                "de edad y que tenga el permiso `Gestionar roles`.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            LOGGER.exception(
                "Error assigning age role guild_id=%s user_id=%s age=%s",
                guild.id,
                member.id,
                self.age_code,
            )

            await interaction.response.send_message(
                "Ocurrió un error al asignar tu rol. "
                "Inténtalo nuevamente.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Tu rol ahora es "
            f"**{self.age_emoji} {self.age_name}**.",
            ephemeral=True,
        )


class AgeView(discord.ui.View):
    """Persistent age selector."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

        for age_code, emoji, age_name in AGE_ROLES:
            self.add_item(
                AgeButton(
                    age_code,
                    emoji,
                    age_name,
                )
            )


def build_age_embed() -> discord.Embed:
    """Build the age self-role information card."""
    embed = discord.Embed(
        title="🔞 Autoroles de edad",
        description=(
            "Selecciona tu rango de edad para recibir automáticamente "
            "el rol correspondiente.\n\n"
            "🔞 **+18**\n"
            "Para miembros mayores de 18 años.\n\n"
            "🔒 **-18**\n"
            "Para miembros menores de 18 años.\n\n"
            "🔄 Puedes cambiar tu selección cuando quieras."
        ),
        color=discord.Color.dark_grey(),
    )

    embed.add_field(
        name="📌 Importante",
        value=(
            "Solo puedes tener **un rol de edad** al mismo tiempo. "
            "Al seleccionar uno nuevo, Odinus retirará el anterior."
        ),
        inline=False,
    )

    embed.add_field(
        name="🏷️ Formato de los roles",
        value="`『🔞』+18`  •  `『🔒』-18`",
        inline=False,
    )

    embed.set_footer(
        text="Odinus • Sistema de autoroles",
    )

    return embed


class EdadCog(commands.Cog):
    """Age self-role commands and persistent selector."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repository = AgeRepository()

    async def cog_load(self) -> None:
        """Initialize age storage."""
        self.repository.initialize()

    @app_commands.command(
        name="edad",
        description="Configura los autoroles de edad.",
    )
    @app_commands.describe(
        canal="Canal donde se publicará el selector de edad.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def edad(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        """Configure and publish the age selector."""
        if interaction.guild is None:
            return

        me = interaction.guild.me

        if me is None:
            await interaction.response.send_message(
                "No pude obtener la información del bot en este servidor.",
                ephemeral=True,
            )
            return

        permissions = canal.permissions_for(me)

        missing_permissions = []

        if not permissions.view_channel:
            missing_permissions.append("Ver canal")

        if not permissions.send_messages:
            missing_permissions.append("Enviar mensajes")

        if not permissions.embed_links:
            missing_permissions.append("Insertar enlaces")

        if not permissions.manage_roles:
            missing_permissions.append("Gestionar roles")

        if missing_permissions:
            await interaction.response.send_message(
                "No tengo los permisos necesarios en ese canal: "
                + ", ".join(missing_permissions)
                + ".",
                ephemeral=True,
            )
            return

        try:
            for _, emoji, age_name in AGE_ROLES:
                name = age_role_name(emoji, age_name)

                existing_role = discord.utils.get(
                    interaction.guild.roles,
                    name=name,
                )

                if existing_role is None:
                    await interaction.guild.create_role(
                        name=name,
                        reason="Creación de roles de edad de Odinus.",
                    )

        except discord.Forbidden:
            await interaction.response.send_message(
                "No puedo crear los roles de edad. "
                "Necesito el permiso `Gestionar roles`.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            LOGGER.exception(
                "Error creating age roles guild_id=%s",
                interaction.guild.id,
            )

            await interaction.response.send_message(
                "Ocurrió un error al crear los roles de edad.",
                ephemeral=True,
            )
            return

        self.repository.set_channel(
            interaction.guild.id,
            canal.id,
        )

        try:
            await canal.send(
                embed=build_age_embed(),
                view=AgeView(),
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "Los roles fueron configurados, pero no pude publicar "
                "el selector en ese canal.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            LOGGER.exception(
                "Error publishing age selector guild_id=%s channel_id=%s",
                interaction.guild.id,
                canal.id,
            )

            await interaction.response.send_message(
                "Los roles fueron configurados, pero ocurrió un error "
                "al publicar el selector.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"🔞 Selector de edad configurado correctamente "
            f"en {canal.mention}.",
            ephemeral=True,
        )

    @edad.error
    async def edad_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle permission errors."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "No tienes permiso para configurar los autoroles de edad.",
                ephemeral=True,
            )
            return

        raise error


async def setup(bot: commands.Bot) -> None:
    """Register the age Cog and persistent button view."""
    await bot.add_cog(EdadCog(bot))
    bot.add_view(AgeView())