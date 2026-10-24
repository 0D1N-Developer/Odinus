"""Video game self-role system for Discord servers."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


# Un mensaje de Discord admite hasta 25 botones, suficiente para esta lista.
GAMES = (
    ("minecraft", "⛏️", "Minecraft"),
    ("terraria", "🌳", "Terraria"),
    ("ark", "🦖", "ARK"),
    ("roblox", "🧱", "Roblox"),
    ("amongus", "📮", "Among Us"),
    ("vrchat", "🥽", "VRChat"),
    ("pvz1", "🌻", "Plants vs. Zombies"),
    ("pvzgw1", "🧟", "PvZ: Garden Warfare"),
    ("pvzgw2", "🌵", "PvZ: Garden Warfare 2"),
    ("pvzbfn", "🏡", "PvZ: Battle for Neighborville"),
    ("lol", "⚔️", "League of Legends"),
    ("gta5", "🚗", "GTA V"),
    ("rocketleague", "🚀", "Rocket League"),
)

GAME_ROLE_LIMIT = 250


def game_role_name(emoji: str, name: str) -> str:
    """Build the standard game role name."""
    return f"『{emoji}』{name}"


class GameButton(discord.ui.Button):
    """Button that toggles one game role."""

    def __init__(
        self,
        game_code: str,
        emoji: str,
        game_name: str,
    ) -> None:
        super().__init__(
            label=game_name,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"odinus:game:{game_code}",
        )

        self.game_code = game_code
        self.game_emoji = emoji
        self.game_name = game_name

    async def callback(self, interaction: discord.Interaction) -> None:
        """Give the game role, or remove it if the member already has it."""
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

        role = discord.utils.get(
            guild.roles,
            name=game_role_name(
                self.game_emoji,
                self.game_name,
            ),
        )

        if role is None:
            await interaction.response.send_message(
                "El rol de este juego no existe actualmente. "
                "Pide a un administrador que vuelva a configurar "
                "el selector.",
                ephemeral=True,
            )
            return

        removing = role in member.roles

        try:
            if removing:
                await member.remove_roles(
                    role,
                    reason="Juego retirado mediante el selector de Odinus.",
                )
            else:
                await member.add_roles(
                    role,
                    reason="Juego seleccionado mediante Odinus.",
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                "No puedo administrar los roles de juegos. "
                "Verifica que mi rol esté por encima de los roles "
                "de juegos y que tenga el permiso `Gestionar roles`.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            LOGGER.exception(
                "Error toggling game role guild_id=%s user_id=%s game=%s",
                guild.id,
                member.id,
                self.game_code,
            )

            await interaction.response.send_message(
                "Ocurrió un error al actualizar tu rol. "
                "Inténtalo nuevamente.",
                ephemeral=True,
            )
            return

        if removing:
            message = (
                f"🎮 Ya no tienes el rol de "
                f"**{self.game_emoji} {self.game_name}**."
            )
        else:
            message = (
                f"🎮 Ahora tienes el rol de "
                f"**{self.game_emoji} {self.game_name}**."
            )

        await interaction.response.send_message(
            message,
            ephemeral=True,
        )


class GameView(discord.ui.View):
    """Persistent video game selector."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

        for game_code, emoji, game_name in GAMES:
            self.add_item(
                GameButton(
                    game_code,
                    emoji,
                    game_name,
                )
            )


def build_games_embed() -> discord.Embed:
    """Build the video game self-role information card."""
    embed = discord.Embed(
        title="🎮 Autoroles de videojuegos",
        description=(
            "Selecciona los juegos que juegas para recibir "
            "automáticamente su rol y encontrar a otros jugadores.\n\n"
            "🔄 Pulsa un botón para **obtener** el rol y vuelve a "
            "pulsarlo para **quitarlo**."
        ),
        color=discord.Color.blurple(),
    )

    embed.add_field(
        name="📌 ¿Cómo funciona?",
        value=(
            "Puedes tener **todos los juegos que quieras** al mismo "
            "tiempo. Pulsa los botones de los juegos que te interesen."
        ),
        inline=False,
    )

    embed.add_field(
        name="🏷️ Formato de los roles",
        value="`『⛏️』Minecraft`",
        inline=False,
    )

    embed.set_footer(
        text="Odinus • Sistema de autoroles",
    )

    return embed


class JuegosCog(commands.Cog):
    """Video game self-role commands and persistent selector."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="juegos",
        description="Publica el selector de autoroles de videojuegos.",
    )
    @app_commands.describe(
        canal="Canal donde se publicará el selector de videojuegos.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def juegos(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        """Create the game roles and publish the selector."""
        if interaction.guild is None:
            return

        guild = interaction.guild
        me = guild.me

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

        existing_names = {role.name for role in guild.roles}

        missing_roles = [
            game_role_name(emoji, name)
            for _, emoji, name in GAMES
            if game_role_name(emoji, name) not in existing_names
        ]

        if len(guild.roles) + len(missing_roles) > GAME_ROLE_LIMIT:
            await interaction.response.send_message(
                f"No hay espacio para crear {len(missing_roles)} roles "
                f"nuevos: Discord permite un máximo de "
                f"{GAME_ROLE_LIMIT} roles por servidor y actualmente "
                f"hay {len(guild.roles)}.",
                ephemeral=True,
            )
            return

        # Crear decenas de roles tarda más de los 3 segundos que Discord
        # concede para responder, así que se difiere la respuesta.
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        try:
            for role_name in missing_roles:
                await guild.create_role(
                    name=role_name,
                    reason="Creación de roles de videojuegos de Odinus.",
                )

        except discord.Forbidden:
            await interaction.followup.send(
                "No puedo crear los roles de juegos. "
                "Necesito el permiso `Gestionar roles`.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            LOGGER.exception(
                "Error creating game roles guild_id=%s",
                guild.id,
            )

            await interaction.followup.send(
                "Ocurrió un error al crear los roles de juegos. "
                "Puedes ejecutar el comando de nuevo: solo se crearán "
                "los roles que falten.",
                ephemeral=True,
            )
            return

        try:
            await canal.send(
                embed=build_games_embed(),
                view=GameView(),
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "Los roles fueron configurados, pero no pude publicar "
                "los selector en ese canal.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            LOGGER.exception(
                "Error publishing game selector guild_id=%s channel_id=%s",
                guild.id,
                canal.id,
            )

            await interaction.followup.send(
                "Los roles fueron configurados, pero ocurrió un error "
                "al publicar el selector.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"🎮 Selector de videojuegos publicado en "
            f"{canal.mention}.\n"
            f"Roles creados: **{len(missing_roles)}** de "
            f"**{len(GAMES)}**.",
            ephemeral=True,
        )

    @juegos.error
    async def juegos_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle permission errors."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "No tienes permiso para configurar los autoroles "
                "de videojuegos.",
                ephemeral=True,
            )
            return

        raise error


async def setup(bot: commands.Bot) -> None:
    """Register the game Cog and persistent button view."""
    await bot.add_cog(JuegosCog(bot))

    bot.add_view(GameView())
