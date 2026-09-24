"""Discord commands for the server information system."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from odinus.services.server import ServerRepository
from odinus.services.server import ServerService


LOGGER = logging.getLogger(__name__)


class GeneralConfigModal(discord.ui.Modal):
    """Modal for general server-card configuration."""

    name_input = discord.ui.TextInput(
        label="Nombre del servidor",
        placeholder="Deja vacío para usar el nombre de Discord.",
        required=False,
        max_length=256,
    )

    description_input = discord.ui.TextInput(
        label="Descripción",
        placeholder="Descripción que aparecerá en la tarjeta.",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=4000,
    )

    website_input = discord.ui.TextInput(
        label="Sitio web",
        placeholder="https://ejemplo.com",
        required=False,
        max_length=2048,
    )

    color_input = discord.ui.TextInput(
        label="Color del Embed",
        placeholder="#2B2D31",
        required=False,
        max_length=7,
    )

    def __init__(
        self,
        service: ServerService,
        guild_id: int,
    ) -> None:
        super().__init__(
            title="Configuración general"
        )

        self.service = service
        self.guild_id = guild_id

        settings = service.get_settings(
            guild_id
        )

        self.name_input.default = (
            settings.get("name") or ""
        )

        self.description_input.default = (
            settings.get("description") or ""
        )

        self.website_input.default = (
            settings.get("website") or ""
        )

        self.color_input.default = (
            settings.get("color") or "#2B2D31"
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        name = self.name_input.value.strip()
        description = self.description_input.value.strip()
        website = self.website_input.value.strip()
        color = self.color_input.value.strip()

        if name:
            self.service.update_setting(
                self.guild_id,
                "name",
                name,
            )
        else:
            self.service.update_setting(
                self.guild_id,
                "name",
                None,
            )

        self.service.update_setting(
            self.guild_id,
            "description",
            description
            or "Información actual de este servidor.",
        )

        if website:
            if not self.service._valid_url(website):
                await interaction.response.send_message(
                    (
                        "❌ El sitio web debe ser una URL válida "
                        "que comience con `http://` o `https://`."
                    ),
                    ephemeral=True,
                )
                return

            self.service.update_setting(
                self.guild_id,
                "website",
                website,
            )
        else:
            self.service.update_setting(
                self.guild_id,
                "website",
                None,
            )

        if color:
            normalized_color = color.lstrip("#")

            try:
                if len(normalized_color) != 6:
                    raise ValueError

                int(normalized_color, 16)

            except ValueError:
                await interaction.response.send_message(
                    (
                        "❌ El color debe estar en formato hexadecimal, "
                        "por ejemplo `#5865F2`."
                    ),
                    ephemeral=True,
                )
                return

            self.service.update_setting(
                self.guild_id,
                "color",
                f"#{normalized_color.upper()}",
            )
        else:
            self.service.update_setting(
                self.guild_id,
                "color",
                "#2B2D31",
            )

        await interaction.response.send_message(
            "✅ Configuración general actualizada.",
            ephemeral=True,
        )


class ImageConfigModal(discord.ui.Modal):
    """Modal for server-card image configuration."""

    thumbnail_input = discord.ui.TextInput(
        label="Logo / Thumbnail",
        placeholder="https://ejemplo.com/logo.png",
        required=False,
        max_length=2048,
    )

    image_input = discord.ui.TextInput(
        label="Banner / Imagen",
        placeholder="https://ejemplo.com/banner.png",
        required=False,
        max_length=2048,
    )

    def __init__(
        self,
        service: ServerService,
        guild_id: int,
    ) -> None:
        super().__init__(
            title="Imágenes de la tarjeta"
        )

        self.service = service
        self.guild_id = guild_id

        settings = service.get_settings(
            guild_id
        )

        self.thumbnail_input.default = (
            settings.get("thumbnail_url") or ""
        )

        self.image_input.default = (
            settings.get("image_url") or ""
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        thumbnail = self.thumbnail_input.value.strip()
        image = self.image_input.value.strip()

        if thumbnail and not self.service._valid_url(
            thumbnail
        ):
            await interaction.response.send_message(
                "❌ La URL del logo no es válida.",
                ephemeral=True,
            )
            return

        if image and not self.service._valid_url(
            image
        ):
            await interaction.response.send_message(
                "❌ La URL del banner no es válida.",
                ephemeral=True,
            )
            return

        self.service.update_setting(
            self.guild_id,
            "thumbnail_url",
            thumbnail or None,
        )

        self.service.update_setting(
            self.guild_id,
            "image_url",
            image or None,
        )

        await interaction.response.send_message(
            "✅ Imágenes actualizadas.",
            ephemeral=True,
        )


class ToggleButton(discord.ui.Button):
    """Button that toggles one server-card setting."""

    def __init__(
        self,
        service: ServerService,
        guild_id: int,
        key: str,
        label: str,
        emoji: str,
        row: int,
    ) -> None:
        self.service = service
        self.guild_id = guild_id
        self.key = key

        settings = service.get_settings(
            guild_id
        )

        enabled = bool(
            settings.get(
                key,
                True,
            )
        )

        super().__init__(
            label=label,
            emoji=emoji,
            style=(
                discord.ButtonStyle.success
                if enabled
                else discord.ButtonStyle.secondary
            ),
            row=row,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        settings = self.service.get_settings(
            self.guild_id
        )

        current = bool(
            settings.get(
                self.key,
                True,
            )
        )

        self.service.update_setting(
            self.guild_id,
            self.key,
            not current,
        )

        await interaction.response.edit_message(
            view=ServerConfigView(
                self.service,
                self.guild_id,
            )
        )


class GeneralButton(discord.ui.Button):
    """Open general configuration."""

    def __init__(
        self,
        service: ServerService,
        guild_id: int,
    ) -> None:
        self.service = service
        self.guild_id = guild_id

        super().__init__(
            label="General",
            emoji="⚙️",
            style=discord.ButtonStyle.primary,
            row=2,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_modal(
            GeneralConfigModal(
                self.service,
                self.guild_id,
            )
        )


class ImageButton(discord.ui.Button):
    """Open image configuration."""

    def __init__(
        self,
        service: ServerService,
        guild_id: int,
    ) -> None:
        self.service = service
        self.guild_id = guild_id

        super().__init__(
            label="Imágenes",
            emoji="🖼️",
            style=discord.ButtonStyle.primary,
            row=2,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_modal(
            ImageConfigModal(
                self.service,
                self.guild_id,
            )
        )


class ResetButton(discord.ui.Button):
    """Restore default configuration."""

    def __init__(
        self,
        service: ServerService,
        guild_id: int,
    ) -> None:
        self.service = service
        self.guild_id = guild_id

        super().__init__(
            label="Restablecer",
            emoji="🔄",
            style=discord.ButtonStyle.danger,
            row=3,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        self.service.reset_settings(
            self.guild_id
        )

        await interaction.response.edit_message(
            content=(
                "⚙️ **Configuración de la tarjeta del servidor**\n\n"
                "La configuración ha sido restaurada "
                "a los valores predeterminados."
            ),
            view=ServerConfigView(
                self.service,
                self.guild_id,
            ),
        )


class ServerConfigView(discord.ui.View):
    """Interactive server-card configuration panel."""

    def __init__(
        self,
        service: ServerService,
        guild_id: int,
    ) -> None:
        super().__init__(
            timeout=300
        )

        self.service = service
        self.guild_id = guild_id

        # Fila 0
        self.add_item(
            ToggleButton(
                service,
                guild_id,
                "show_online",
                "En línea",
                "🟢",
                row=0,
            )
        )

        self.add_item(
            ToggleButton(
                service,
                guild_id,
                "show_bots",
                "Bots",
                "🤖",
                row=0,
            )
        )

        self.add_item(
            ToggleButton(
                service,
                guild_id,
                "show_boosts",
                "Boosts",
                "💎",
                row=0,
            )
        )

        self.add_item(
            ToggleButton(
                service,
                guild_id,
                "show_channels",
                "Canales",
                "📁",
                row=0,
            )
        )

        self.add_item(
            ToggleButton(
                service,
                guild_id,
                "show_roles",
                "Roles",
                "🎭",
                row=0,
            )
        )

        # Fila 1
        self.add_item(
            ToggleButton(
                service,
                guild_id,
                "show_emojis",
                "Emojis",
                "😀",
                row=1,
            )
        )

        self.add_item(
            ToggleButton(
                service,
                guild_id,
                "show_stickers",
                "Stickers",
                "🎨",
                row=1,
            )
        )

        self.add_item(
            ToggleButton(
                service,
                guild_id,
                "show_owner",
                "Propietario",
                "👑",
                row=1,
            )
        )

        self.add_item(
            ToggleButton(
                service,
                guild_id,
                "show_created",
                "Creación",
                "📅",
                row=1,
            )
        )

        # Fila 2
        self.add_item(
            GeneralButton(
                service,
                guild_id,
            )
        )

        self.add_item(
            ImageButton(
                service,
                guild_id,
            )
        )

        # Fila 3
        self.add_item(
            ResetButton(
                service,
                guild_id,
            )
        )


class ServerGroup(app_commands.Group):
    """Commands for server information."""

    def __init__(
        self,
        service: ServerService,
    ) -> None:
        super().__init__(
            name="server",
            description=(
                "Muestra y administra la información del servidor."
            ),
        )

        self.service = service

    @app_commands.command(
        name="info",
        description="Muestra la información actual del servidor.",
    )
    @app_commands.guild_only()
    async def info(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Display the current server information."""
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                (
                    "Este comando solo puede utilizarse "
                    "dentro de un servidor."
                ),
                ephemeral=True,
            )
            return

        embed = self.service.build_embed(
            guild
        )

        await interaction.response.send_message(
            embed=embed,
        )

    @app_commands.command(
        name="activar",
        description="Activa la tarjeta permanente de información.",
    )
    @app_commands.describe(
        canal="Canal donde se publicará la tarjeta permanente.",
    )
    @app_commands.default_permissions(
        administrator=True,
    )
    @app_commands.guild_only()
    async def activar(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        """Activate the permanent server information card."""
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                (
                    "Este comando solo puede utilizarse "
                    "dentro de un servidor."
                ),
                ephemeral=True,
            )
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "No tienes permisos para utilizar este comando.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True,
        )

        try:
            message = await self.service.activate(
                guild=guild,
                channel=canal,
            )

        except discord.Forbidden:
            await interaction.followup.send(
                (
                    "No tengo permisos suficientes para publicar, "
                    "editar o eliminar la tarjeta en ese canal."
                ),
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            LOGGER.exception(
                "Discord API error while activating server card "
                "for guild %s.",
                guild.id,
            )

            await interaction.followup.send(
                "Discord rechazó la operación al activar la tarjeta.",
                ephemeral=True,
            )
            return

        except Exception:
            LOGGER.exception(
                "Unexpected error while activating server card "
                "for guild %s.",
                guild.id,
            )

            await interaction.followup.send(
                (
                    "Ocurrió un error inesperado al activar "
                    "la tarjeta."
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            (
                f"✅ Tarjeta de información activada en "
                f"{canal.mention}.\n"
                f"El mensaje permanente es `{message.id}`."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="desactivar",
        description="Desactiva la tarjeta permanente de información.",
    )
    @app_commands.default_permissions(
        administrator=True,
    )
    @app_commands.guild_only()
    async def desactivar(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Deactivate the permanent server information card."""
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                (
                    "Este comando solo puede utilizarse "
                    "dentro de un servidor."
                ),
                ephemeral=True,
            )
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "No tienes permisos para utilizar este comando.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True,
        )

        try:
            success = self.service.repository.set_enabled(
                guild.id,
                False,
            )

        except Exception:
            LOGGER.exception(
                "Unexpected error while disabling server card "
                "for guild %s.",
                guild.id,
            )

            await interaction.followup.send(
                (
                    "Ocurrió un error inesperado al desactivar "
                    "la tarjeta."
                ),
                ephemeral=True,
            )
            return

        if not success:
            await interaction.followup.send(
                (
                    "No hay ninguna tarjeta permanente configurada "
                    "en este servidor."
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "✅ La tarjeta permanente de información ha sido desactivada.",
            ephemeral=True,
        )

    @app_commands.command(
        name="configurar",
        description="Configura la tarjeta de información del servidor.",
    )
    @app_commands.default_permissions(
        administrator=True,
    )
    @app_commands.guild_only()
    async def configurar(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Open the server-card configuration panel."""
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                (
                    "Este comando solo puede utilizarse "
                    "dentro de un servidor."
                ),
                ephemeral=True,
            )
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "No tienes permisos para utilizar este comando.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            (
                "⚙️ **Configuración de la tarjeta del servidor**\n\n"
                "Utiliza los botones para personalizar la tarjeta "
                "permanente.\n\n"
                "🟢 Los botones de estadísticas activan o desactivan "
                "cada información.\n"
                "⚙️ **General** permite cambiar nombre, descripción, "
                "sitio web y color.\n"
                "🖼️ **Imágenes** permite configurar logo y banner.\n"
                "🔄 **Restablecer** devuelve todo a los valores "
                "predeterminados."
            ),
            view=ServerConfigView(
                self.service,
                guild.id,
            ),
            ephemeral=True,
        )


class ServerCog(commands.Cog):
    """Cog responsible for the server information system."""

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

        self.repository = ServerRepository()
        self.repository.initialize()

        self.service = ServerService(
            bot=self.bot,
            repository=self.repository,
        )

        self.server_group = ServerGroup(
            service=self.service,
        )

    async def cog_load(self) -> None:
        """Load the server information system."""
        self.bot.tree.add_command(
            self.server_group,
        )

        self.service.start()

        LOGGER.info(
            "Server information system loaded."
        )

    async def cog_unload(self) -> None:
        """Unload the server information system."""
        self.bot.tree.remove_command(
            self.server_group.name,
            type=discord.AppCommandType.chat_input,
        )

        await self.service.stop()

        LOGGER.info(
            "Server information system unloaded."
        )


async def setup(
    bot: commands.Bot,
) -> None:
    """Load the server cog."""
    await bot.add_cog(
        ServerCog(bot)
    )