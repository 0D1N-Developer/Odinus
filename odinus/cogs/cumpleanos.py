"""Birthday registration and scheduled announcements for Discord servers."""

import calendar
from datetime import date, datetime, time
import logging
from math import ceil
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from odinus.services.birthdays import Birthday, BirthdayRepository

LOGGER = logging.getLogger(__name__)
MEXICO_CITY = ZoneInfo("America/Mexico_City")
MONTH_NAMES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
PAGE_SIZE = 10


class BirthdayListView(discord.ui.View):
    """Private pagination controls for a server's birthday list."""

    def __init__(self, user_id: int, birthdays: list[Birthday]) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.birthdays = birthdays
        self.page = 0
        self.total_pages = ceil(len(birthdays) / PAGE_SIZE)
        self._update_buttons()

    def build_embed(self) -> discord.Embed:
        """Build one page containing up to ten upcoming birthdays."""
        start = self.page * PAGE_SIZE
        page_birthdays = self.birthdays[start : start + PAGE_SIZE]
        entries = [
            f"`{start + position:02d}.` <@{birthday.user_id}> — "
            f"{birthday.day} de {MONTH_NAMES[birthday.month - 1]}"
            for position, birthday in enumerate(page_birthdays, start=1)
        ]
        embed = discord.Embed(
            title="🎂 Próximos cumpleaños",
            description="\n".join(entries),
            color=discord.Color.orange(),
        )
        embed.set_footer(
            text=f"Página {self.page + 1} de {self.total_pages} • "
            f"{len(self.birthdays)} registro(s)"
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Limit pagination controls to the member who requested the list."""
        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "Solo la persona que abrió esta lista puede navegarla.", ephemeral=True
        )
        return False

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Show the preceding page of birthdays."""
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Show the following page of birthdays."""
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    def _update_buttons(self) -> None:
        """Disable navigation controls at the beginning and end of the list."""
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.total_pages - 1


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
        name="lista",
        description="Muestra los próximos cumpleaños registrados.",
    )
    @app_commands.guild_only()
    async def lista(self, interaction: discord.Interaction) -> None:
        """Show birthdays in upcoming order, ten entries per page."""
        if interaction.guild_id is None:
            return

        birthdays = self.repository.birthdays_in_guild(interaction.guild_id)
        if not birthdays:
            await interaction.response.send_message(
                "Aún no hay cumpleaños registrados en este servidor.",
                ephemeral=True,
            )
            return

        today = datetime.now(MEXICO_CITY).date()
        birthdays.sort(key=lambda birthday: self._next_birthday_date(birthday, today))
        view = BirthdayListView(interaction.user.id, birthdays)
        await interaction.response.send_message(
            embed=view.build_embed(), view=view, ephemeral=True
        )

    @staticmethod
    def _next_birthday_date(birthday: Birthday, today: date) -> date:
        """Find the next observed birthday date, including leap-day handling."""
        birthday_date = CumpleanosCog._birthday_date_for_year(birthday, today.year)
        if birthday_date < today:
            birthday_date = CumpleanosCog._birthday_date_for_year(
                birthday, today.year + 1
            )
        return birthday_date

    @staticmethod
    def _birthday_date_for_year(birthday: Birthday, year: int) -> date:
        """Observe February 29 birthdays on February 28 in non-leap years."""
        is_leap_day_in_a_common_year = (
            birthday.month == 2 and birthday.day == 29 and not calendar.isleap(year)
        )
        day = 28 if is_leap_day_in_a_common_year else birthday.day
        return date(year, birthday.month, day)

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
