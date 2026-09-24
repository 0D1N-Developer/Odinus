"""General slash commands for Odinus."""

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands


class GeneralCog(commands.Cog):
    """Commands that provide bot status and guidance."""

    @app_commands.command(
        name="ping",
        description="Comprueba que Odinus está activo.",
    )
    async def ping(self, interaction: discord.Interaction) -> None:
        """Confirm that the bot is responding."""
        await interaction.response.send_message(
            "Odinus está activo."
        )

    @app_commands.command(
        name="clear",
        description="Elimina mensajes recientes de este canal.",
    )
    @app_commands.describe(
        cantidad="Cantidad de mensajes a eliminar (de 1 a 100)."
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def clear(
        self,
        interaction: discord.Interaction,
        cantidad: app_commands.Range[int, 1, 100],
    ) -> None:
        """Delete recent messages from the channel where the command is used."""
        if not isinstance(
            interaction.channel,
            (discord.TextChannel, discord.Thread),
        ):
            await interaction.response.send_message(
                "Este comando solo puede usarse en un canal de texto.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        cutoff = discord.utils.utcnow() - timedelta(days=14)

        try:
            deleted_messages = await interaction.channel.purge(
                limit=cantidad,
                check=lambda message: message.created_at > cutoff,
                bulk=True,
            )
        except discord.Forbidden:
            await interaction.edit_original_response(
                content=(
                    "No tengo permiso para eliminar mensajes "
                    "en este canal."
                )
            )
            return

        await interaction.edit_original_response(
            content=(
                f"Se eliminaron {len(deleted_messages)} mensaje(s)."
            )
        )

    @app_commands.command(
        name="slowmode",
        description="Configura el modo lento de este canal.",
    )
    @app_commands.describe(
        segundos="Duración en segundos (0 para desactivarlo)."
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def slowmode(
        self,
        interaction: discord.Interaction,
        segundos: app_commands.Range[int, 0, 21600],
    ) -> None:
        """Set the native slowmode delay for the current text channel."""
        if not isinstance(
            interaction.channel,
            discord.TextChannel,
        ):
            await interaction.response.send_message(
                "Este comando solo puede usarse en un canal de texto.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.channel.edit(
                slowmode_delay=segundos,
                reason=f"Modo lento configurado por {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.edit_original_response(
                content=(
                    "No tengo permiso para configurar el modo lento "
                    "en este canal."
                )
            )
            return

        if segundos == 0:
            content = "Modo lento desactivado."
        else:
            content = (
                f"Modo lento configurado en {segundos} segundo(s)."
            )

        await interaction.edit_original_response(
            content=content
        )

    @app_commands.command(
        name="ayuda",
        description="Muestra los comandos disponibles.",
    )
    async def ayuda(self, interaction: discord.Interaction) -> None:
        """Show the commands available to the current user."""
        is_admin = (
            interaction.guild is not None
            and isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.administrator
        )

        user_commands = (
            "**👤 Comandos para usuarios**\n"
            "`/ping` — Comprueba que Odinus está activo.\n"
            "`/ayuda` — Muestra los comandos disponibles.\n"
            "`/redes` — Muestra las redes sociales de Black Tibii.\n"
            "`/perfil [usuario]` — Muestra el perfil visual de un miembro.\n"
            "`/nivel [usuario]` — Consulta el nivel, XP y progreso de un miembro.\n"
            "`/cumpleaños registrar` — Registra una fecha de cumpleaños.\n"
            "`/cumpleaños lista` — Consulta los cumpleaños registrados."
        )

        admin_commands = (
            "\n\n"
            "**🛠️ Comandos para administradores**\n"
            "`/publicar` — Publica un mensaje en un canal seleccionado.\n"
            "`/clear` — Elimina mensajes recientes del canal.\n"
            "`/slowmode` — Configura el modo lento del canal.\n"
            "`/cumpleaños configurar_canal` — Configura el canal de avisos de cumpleaños.\n"
            "`/invitaciones configurar_canal` — Configura el canal de seguimiento de invitaciones.\n"
            "`/paises` — Configura el selector de autoroles de países.\n"
            "`/edad` — Configura el selector de autoroles de edad.\n"
            "`/niveles activar` — Activa la obtención automática de XP.\n"
            "`/niveles desactivar` — Desactiva la obtención automática de XP.\n"
            "`/nivel_administrar` — Administra el nivel y XP de un miembro.\n"
            "`/recompensa añadir` — Añade una recompensa por nivel.\n"
            "`/recompensa editar` — Edita una recompensa por nivel.\n"
            "`/recompensa eliminar` — Elimina una recompensa por nivel.\n"
            "`/recompensa lista` — Muestra las recompensas configuradas.\n"
            "`/anuncios configurar` — Configura una plataforma y su canal de anuncios.\n"
            "`/anuncios activar` — Activa una plataforma de anuncios.\n"
            "`/anuncios desactivar` — Desactiva una plataforma de anuncios.\n"
            "`/anuncios comprobar` — Comprueba manualmente una integración.\n"
            "`/anuncios estado` — Muestra el estado de las plataformas configuradas."
        )

        announcement_info = (
            "\n\n"
            "**📢 Centro de anuncios**\n"
            "YouTube • Twitch • Instagram • Facebook • Spotify"
        )

        if is_admin:
            content = (
                "**Odinus • Comandos disponibles**\n\n"
                f"{user_commands}"
                f"{admin_commands}"
                f"{announcement_info}"
            )
        else:
            content = (
                "**Odinus • Comandos disponibles**\n\n"
                f"{user_commands}"
            )

        await interaction.response.send_message(
            content,
            ephemeral=True,
        )

    @clear.error
    async def clear_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Explain failed administrator checks without exposing details publicly."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "No tienes permiso para utilizar este comando.",
                ephemeral=True,
            )
            return

        raise error

    @slowmode.error
    async def slowmode_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Explain failed channel-management checks privately."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "No tienes permiso para configurar el modo lento.",
                ephemeral=True,
            )
            return

        raise error


async def setup(bot: commands.Bot) -> None:
    """Register this command module with Odinus."""
    await bot.add_cog(GeneralCog())