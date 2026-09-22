"""Country self-role system for Discord servers."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from odinus.services.paises import CountryRepository

LOGGER = logging.getLogger(__name__)


COUNTRIES = (
    ("AR", "🇦🇷", "Argentina"),
    ("BO", "🇧🇴", "Bolivia"),
    ("CL", "🇨🇱", "Chile"),
    ("CO", "🇨🇴", "Colombia"),
    ("CR", "🇨🇷", "Costa Rica"),
    ("CU", "🇨🇺", "Cuba"),
    ("DO", "🇩🇴", "República Dominicana"),
    ("EC", "🇪🇨", "Ecuador"),
    ("SV", "🇸🇻", "El Salvador"),
    ("ES", "🇪🇸", "España"),
    ("US", "🇺🇸", "Estados Unidos"),
    ("GT", "🇬🇹", "Guatemala"),
    ("GQ", "🇬🇶", "Guinea Ecuatorial"),
    ("HN", "🇭🇳", "Honduras"),
    ("MX", "🇲🇽", "México"),
    ("NI", "🇳🇮", "Nicaragua"),
    ("PA", "🇵🇦", "Panamá"),
    ("PY", "🇵🇾", "Paraguay"),
    ("PE", "🇵🇪", "Perú"),
    ("PR", "🇵🇷", "Puerto Rico"),
    ("UY", "🇺🇾", "Uruguay"),
    ("VE", "🇻🇪", "Venezuela"),
    ("CA", "🇨🇦", "Canadá"),
)


def role_name(emoji: str, country: str) -> str:
    """Build the standard country role name."""
    return f"『{emoji}』{country}"


class CountryButton(discord.ui.Button):
    """Button that assigns one country role."""

    def __init__(
        self,
        country_code: str,
        emoji: str,
        country_name: str,
    ) -> None:
        super().__init__(
            label=country_name,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"odinus:country:{country_code}",
        )

        self.country_code = country_code
        self.country_name = country_name
        self.country_emoji = emoji

    async def callback(self, interaction: discord.Interaction) -> None:
        """Assign the selected country role and remove previous country roles."""
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

        selected_role_name = role_name(
            self.country_emoji,
            self.country_name,
        )

        selected_role = discord.utils.get(
            guild.roles,
            name=selected_role_name,
        )

        if selected_role is None:
            await interaction.response.send_message(
                "El rol de este país no existe actualmente. "
                "Pide a un administrador que vuelva a configurar "
                "el selector.",
                ephemeral=True,
            )
            return

        country_role_names = {
            role_name(emoji, name)
            for _, emoji, name in COUNTRIES
        }

        roles_to_remove = [
            role
            for role in member.roles
            if role.name in country_role_names
            and role != selected_role
        ]

        try:
            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove,
                    reason="Cambio de país mediante el selector de Odinus.",
                )

            if selected_role not in member.roles:
                await member.add_roles(
                    selected_role,
                    reason="Selección de país mediante Odinus.",
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                "No puedo administrar los roles de país. "
                "Verifica que mi rol esté por encima de los roles "
                "de país y que tenga el permiso `Gestionar roles`.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            LOGGER.exception(
                "Error assigning country role guild_id=%s user_id=%s country=%s",
                guild.id,
                member.id,
                self.country_code,
            )

            await interaction.response.send_message(
                "Ocurrió un error al asignar tu rol. "
                "Inténtalo nuevamente.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"🌎 Tu país ahora es "
            f"**{self.country_emoji} {self.country_name}**.",
            ephemeral=True,
        )


class CountryView(discord.ui.View):
    """Persistent country selector."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

        for country_code, emoji, country_name in COUNTRIES:
            self.add_item(
                CountryButton(
                    country_code,
                    emoji,
                    country_name,
                )
            )


def build_country_embed() -> discord.Embed:
    """Build the public country self-role information card."""
    embed = discord.Embed(
        title="🌎 Autoroles de país",
        description=(
            "Selecciona el país con el que te identificas para recibir "
            "automáticamente su rol.\n\n"
            "🔄 Puedes cambiar tu país cuando quieras. "
            "Al seleccionar uno nuevo, Odinus retirará automáticamente "
            "tu rol de país anterior."
        ),
        color=discord.Color.blurple(),
    )

    embed.add_field(
        name="📌 ¿Cómo funciona?",
        value=(
            "Pulsa el botón correspondiente a tu país. "
            "Odinus se encargará de asignarte el rol."
        ),
        inline=False,
    )

    embed.add_field(
        name="🏷️ Formato de los roles",
        value="`『🇲🇽』México`",
        inline=False,
    )

    embed.set_footer(
        text="Odinus • Sistema de autoroles",
    )

    return embed


class PaisesCog(commands.Cog):
    """Country self-role commands and persistent selector."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repository = CountryRepository()

    async def cog_load(self) -> None:
        """Initialize country storage."""
        self.repository.initialize()

    @app_commands.command(
        name="paises",
        description="Publica el selector de autoroles de países.",
    )
    @app_commands.describe(
        canal="Canal donde se publicará el selector de países.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def paises(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        """Configure and publish the country selector."""
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
            for _, emoji, country_name in COUNTRIES:
                name = role_name(emoji, country_name)

                existing_role = discord.utils.get(
                    interaction.guild.roles,
                    name=name,
                )

                if existing_role is None:
                    await interaction.guild.create_role(
                        name=name,
                        reason="Creación de roles de país de Odinus.",
                    )

        except discord.Forbidden:
            await interaction.response.send_message(
                "No puedo crear los roles de país. "
                "Necesito el permiso `Gestionar roles`.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            LOGGER.exception(
                "Error creating country roles guild_id=%s",
                interaction.guild.id,
            )

            await interaction.response.send_message(
                "Ocurrió un error al crear los roles de país.",
                ephemeral=True,
            )
            return

        self.repository.set_channel(
            interaction.guild.id,
            canal.id,
        )

        try:
            await canal.send(
                embed=build_country_embed(),
                view=CountryView(),
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
                "Error publishing country selector guild_id=%s channel_id=%s",
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
            f"🌎 Selector de países configurado correctamente "
            f"en {canal.mention}.",
            ephemeral=True,
        )

    @paises.error
    async def paises_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle permission errors for the configuration command."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "No tienes permiso para configurar los autoroles de países.",
                ephemeral=True,
            )
            return

        raise error


async def setup(bot: commands.Bot) -> None:
    """Register the country Cog and persistent button view."""
    await bot.add_cog(PaisesCog(bot))
    bot.add_view(CountryView())