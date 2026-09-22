"""Birthday registration and scheduled announcements for Discord servers."""

import calendar
from datetime import datetime, time
import logging
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from odinus.services.birthdays import BirthdayRepository

LOGGER = logging.getLogger(__name__)
MEXICO_CITY = ZoneInfo("America/Mexico_City")


class CumpleanosCog(commands.GroupCog, group_name="cumpleaños", group_description="Gestiona los cumpleaños del servidor."):
    """Commands and scheduled notices for member birthdays."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repository = BirthdayRepository()

    async def cog_load(self) -> None:
        """Initialize storage and start the Mexico City daily announcement task."""
        self.repository.initialize()
        self.announce_birthdays.start()

    def cog_unload(self) -> None:
        """Stop the scheduled task when the extension unloads."""
        self.announce_birthdays.cancel()

    @app_commands.command(name="registrar", description="Registra o actualiza tu cumpleaños.")
    @app_commands.describe(
        dia="Día de nacimiento.",
        mes="Mes de nacimiento.",
        año="Año de nacimiento.",
    )
    @app_commands.guild_only()
    async def registrar(
        self,
        interaction: discord.Interaction,
        dia: app_commands.Range[int, 1, 31],
        mes: app_commands.Range[int, 1, 12],
        año: app_commands.Range[int, 1900, 2100],
    ) -> None:
        """Store the requesting user's birthday for this server."""
        if interaction.guild_id is None:
            return

        try:
            datetime(año, mes, dia)
        except ValueError:
            await interaction.response.send_message(
                "La fecha indicada no es válida.", ephemeral=True
            )
            return

        self.repository.save_birthday(interaction.guild_id, interaction.user.id, dia, mes, año)
        await interaction.response.send_message(
            f"Tu fecha de nacimiento quedó registrada: {dia:02d}/{mes:02d}/{año}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="configurar_canal",
        description="Configura el canal de avisos de cumpleaños.",
    )
    @app_commands.describe(canal="Canal público donde se anunciarán los cumpleaños.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def configurar_canal(
        self, interaction: discord.Interaction, canal: discord.TextChannel
    ) -> None:
        """Set the birthday channel from a private administrator channel."""
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "Este comando solo puede usarse desde un canal privado del servidor.",
                ephemeral=True,
            )
            return

        if interaction.channel.permissions_for(interaction.guild.default_role).view_channel:
            await interaction.response.send_message(
                "Utiliza este comando desde un canal privado de administración.",
                ephemeral=True,
            )
            return

        self.repository.set_announcement_channel(interaction.guild.id, canal.id)
        await interaction.response.send_message(
            f"Los cumpleaños se anunciarán en {canal.mention}.", ephemeral=True
        )

    @configurar_canal.error
    async def configurar_canal_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Respond privately if an administrator check fails."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "No tienes permiso para configurar el canal de cumpleaños.",
                ephemeral=True,
            )
            return
        raise error

    @tasks.loop(time=time(hour=0, minute=0, tzinfo=MEXICO_CITY))
    async def announce_birthdays(self) -> None:
        """Announce birthdays once per calendar day in Mexico City."""
        today = datetime.now(MEXICO_CITY).date()
        is_leap_year = calendar.isleap(today.year)

        for guild_id, channel_id in self.repository.configured_channels():
            guild = self.bot.get_guild(guild_id)
            channel = self.bot.get_channel(channel_id)
            if guild is None or not isinstance(channel, discord.TextChannel):
                LOGGER.warning(
                    "Birthday announcement destination unavailable for guild_id=%s.",
                    guild_id,
                )
                continue

            birthdays = self.repository.birthdays_for_date(
                guild_id, today.day, today.month
            )
            if today.month == 2 and today.day == 28 and not is_leap_year:
                birthdays.extend(self.repository.leap_day_birthdays(guild_id))

            for birthday in birthdays:
                await channel.send(
                    f"🎉 ¡Feliz cumpleaños, <@{birthday.user_id}>! 🎂"
                )

    @announce_birthdays.before_loop
    async def before_announce_birthdays(self) -> None:
        """Wait until the Discord connection is ready before sending notices."""
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    """Register the birthday command group with Odinus."""
    await bot.add_cog(CumpleanosCog(bot))
