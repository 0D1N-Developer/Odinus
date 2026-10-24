"""Minecraft server integration through the Odin-Discord plugin."""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from odinus.integrations.minecraft import (
    BridgeError,
    BridgeUnavailable,
    MinecraftBridge,
)
from odinus.services.minecraft import (
    MinecraftGuildSettings,
    MinecraftLink,
    MinecraftRepository,
)

LOGGER = logging.getLogger(__name__)

MEXICO_CITY = ZoneInfo("America/Mexico_City")

# Debe coincidir con link.code_length en la config de Odin-Discord.
LINK_CODE_LENGTH = 6
# Sin letras ni números que se confundan (O/0, I/1).
LINK_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
NICK_PATTERN = re.compile(r"^[A-Za-z0-9_.*-]{1,20}$")
ADDRESS_PATTERN = re.compile(r"^[A-Za-z0-9.-]{1,90}(:\d{1,5})?$")

# Las líneas que llegan en este intervalo se juntan en un solo mensaje.
FLUSH_DELAY = 1.5
# Discord limita las ediciones; el mensaje de estado se edita como mucho
# una vez cada este número de segundos.
STATUS_EDIT_INTERVAL = 5
MESSAGE_LIMIT = 2000
MAX_AMOUNT = 1_000_000_000_000

RESET = "\x1b[0m"
GRAY = "\x1b[0;30m"
RED = "\x1b[0;31m"
GREEN = "\x1b[0;32m"
YELLOW = "\x1b[0;33m"
BLUE = "\x1b[0;34m"
PINK = "\x1b[0;35m"
CYAN = "\x1b[0;36m"

CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")

ERROR_MESSAGES = {
    "not_linked": "Esa cuenta no está vinculada.",
    "player_offline": "El jugador no está conectado.",
    "insufficient_funds": "No hay saldo suficiente para esa operación.",
    "invalid_amount": (
        "Cantidad no válida: está fuera del mínimo o del máximo "
        "que permite Odin-Economy."
    ),
    "unavailable": (
        "Esa función no está disponible ahora mismo en el servidor "
        "(el plugin necesario no está cargado)."
    ),
    "not_found": "No se encontró esa cuenta en el servidor de Minecraft.",
    "internal": "Ocurrió un error interno en el servidor de Minecraft.",
    "invalid_request": "El servidor rechazó los datos enviados.",
    "disabled": "Esa función está desactivada en la configuración del plugin.",
    "unsupported": "El plugin no reconoce esa operación. ¿Está actualizado?",
}

OFFLINE_MESSAGE = "🔴 El servidor de Minecraft no está conectado ahora mismo."


def clean_text(text: str, limit: int = 500) -> str:
    """Make plugin text safe to show inside a Discord code block."""
    text = CONTROL_CHARACTERS.sub(" ", str(text))
    # Un ``` dentro del texto cerraría el bloque de código.
    text = text.replace("`", "ˋ")

    if len(text) > limit:
        text = text[: limit - 1] + "…"

    return text


CONSOLE_LINE = re.compile(r"^\[(\d{2}:\d{2}:\d{2}) (\w+)\]: ?(.*)$")
LEVEL_COLORS = {
    "WARN": YELLOW,
    "WARNING": YELLOW,
    "ERROR": RED,
    "SEVERE": RED,
}


def color_console_line(line: str) -> str:
    """Color a ``[HH:mm:ss LEVEL]: message`` server console line."""
    match = CONSOLE_LINE.match(line)

    if match is None:
        return line

    time, level, message = match.groups()
    color = LEVEL_COLORS.get(level.upper(), "")

    return (
        f"{GRAY}[{time}]{RESET} {color or CYAN}{level}{RESET} "
        f"{color}{message}{RESET if color else ''}"
    )


def describe_error(error: Exception) -> str:
    """Translate a bridge error into a message for the user."""
    if isinstance(error, BridgeUnavailable):
        return OFFLINE_MESSAGE

    if isinstance(error, BridgeError):
        return "❌ " + ERROR_MESSAGES.get(
            error.code,
            f"El servidor respondió con un error ({error.code}).",
        )

    return "❌ Ocurrió un error inesperado."


def now_text() -> str:
    """Return the current time for console-style lines."""
    return datetime.now(MEXICO_CITY).strftime("%H:%M:%S")


def format_amount(amount: int, currency: str) -> str:
    """Format a money amount."""
    return f"{amount:,} {currency}"


def skin_url(name: str) -> str:
    """Return the head image of a player."""
    return f"https://mc-heads.net/avatar/{name}/64"


TERMINAL_OPENING = "```ansi\n"
TERMINAL_CLOSING = "\n```"
ROOM = MESSAGE_LIMIT - len(TERMINAL_OPENING) - len(TERMINAL_CLOSING)


def render_terminal(lines: list[str]) -> str:
    """Wrap lines in an ANSI code block."""
    return TERMINAL_OPENING + "\n".join(lines) + TERMINAL_CLOSING


def terminal_fits(lines: list[str]) -> bool:
    """Return whether the lines fit in one Discord message."""
    return len("\n".join(lines)) <= ROOM


def build_link_intro_embed(settings: MinecraftGuildSettings) -> discord.Embed:
    """Build the welcome card of the account-linking channel."""
    embed = discord.Embed(
        title="🔗 Vincula tu cuenta de Minecraft",
        description=(
            "Vincula tu cuenta de Discord con tu jugador de Minecraft "
            "para poder **entrar al servidor** y usar sus funciones "
            "desde Discord."
        ),
        color=discord.Color.green(),
    )

    embed.add_field(
        name="📝 Pasos",
        value=(
            "**1.** Escribe aquí `/minecraft vincular nick:TuNick`.\n"
            "**2.** Odinus te dará un **código** (solo lo ves tú) y te "
            "añadirá a la whitelist.\n"
            "**3.** Entra al servidor con ese nick e **inicia sesión**.\n"
            "**4.** Escribe en el chat del juego `/vincular CÓDIGO`.\n"
            "**5.** ¡Listo! Odinus te avisará por mensaje privado."
        ),
        inline=False,
    )

    embed.add_field(
        name="⏳ Importante",
        value=(
            "• El código caduca a los **10 minutos**; si caduca, pide otro.\n"
            "• Cada cuenta de Discord se vincula con **un solo jugador**.\n"
            "• Si juegas desde **Bedrock**, usa tu nick tal como aparece "
            "en el juego."
        ),
        inline=False,
    )

    embed.add_field(
        name="🧰 Comandos",
        value=(
            "`/minecraft vincular` — Vincula tu cuenta.\n"
            "`/minecraft desvincular` — Quita el vínculo y te saca de la "
            "whitelist.\n"
            "`/minecraft perfil` — Muestra tu jugador, rango y dinero.\n"
            "`/minecraft estado` — Mira si el servidor está encendido."
        ),
        inline=False,
    )

    if settings.economy_channel_id:
        embed.add_field(
            name="💰 Economía",
            value=(
                f"Ya vinculado, consulta tu dinero en "
                f"<#{settings.economy_channel_id}>."
            ),
            inline=False,
        )

    embed.set_footer(text="Odinus • Minecraft")
    return embed


def build_economy_intro_embed(settings: MinecraftGuildSettings) -> discord.Embed:
    """Build the welcome card of the economy channel."""
    link_place = (
        f"en <#{settings.link_channel_id}>"
        if settings.link_channel_id
        else "con `/minecraft vincular`"
    )

    embed = discord.Embed(
        title="💰 Economía del servidor de Minecraft",
        description=(
            "En este canal puedes consultar el dinero que tienes en el "
            "servidor de Minecraft sin necesidad de entrar al juego."
        ),
        color=discord.Color.gold(),
    )

    embed.add_field(
        name="👛 Cartera y 🏦 banco",
        value=(
            "**Cartera:** el dinero que llevas encima para pagar y comprar.\n"
            "**Banco:** el dinero que tienes guardado.\n"
            "Para moverlo entre cartera y banco usa `/economy` dentro del "
            "juego."
        ),
        inline=False,
    )

    embed.add_field(
        name="🧰 Comandos",
        value=(
            "`/minecraft saldo` — Tu cartera, banco y total.\n"
            "`/minecraft saldo usuario:@alguien` — El saldo de otro miembro.\n"
            "`/minecraft top` — Los jugadores con más dinero.\n"
            "`/minecraft perfil` — Tu jugador, rango y dinero."
        ),
        inline=False,
    )

    embed.add_field(
        name="🔗 Antes de empezar",
        value=f"Necesitas tener tu cuenta vinculada: hazlo {link_place}.",
        inline=False,
    )

    embed.set_footer(text="Odinus • Odin Economy")
    return embed


class LineBuffer:
    """Show console-style lines as a running terminal in each channel.

    New lines are appended by editing the last terminal message. A new
    message is only started when the current one is full (Discord allows
    2000 characters) or when something else was posted below it.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._lines: dict[int, list[str]] = {}
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        # Último mensaje de terminal de cada canal y las líneas que muestra.
        self._open: dict[int, tuple[discord.Message, list[str]]] = {}

    def add(self, channel_id: int, line: str) -> None:
        """Queue a line; it is shown together with the next ones."""
        self._lines.setdefault(channel_id, []).append(line[:ROOM])

        if channel_id not in self._tasks:
            self._tasks[channel_id] = asyncio.create_task(
                self._flush(channel_id)
            )

    def interrupt(self, channel_id: int) -> None:
        """Something else stays below the terminal: start a new message."""
        self._open.pop(channel_id, None)

    def cancel(self) -> None:
        """Stop pending sends."""
        for task in self._tasks.values():
            task.cancel()

        self._tasks.clear()
        self._lines.clear()
        self._open.clear()

    async def _flush(self, channel_id: int) -> None:
        await asyncio.sleep(FLUSH_DELAY)
        await self.bot.wait_until_ready()

        lock = self._locks.setdefault(channel_id, asyncio.Lock())

        async with lock:
            self._tasks.pop(channel_id, None)
            pending = self._lines.pop(channel_id, [])
            channel = self.bot.get_channel(channel_id)

            if not pending or not isinstance(channel, discord.abc.Messageable):
                return

            try:
                pending = await self._append_to_open(channel_id, pending)

                for lines in self._split(pending):
                    message = await channel.send(
                        render_terminal(lines),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    self._open[channel_id] = (message, lines)

            except discord.HTTPException:
                self._open.pop(channel_id, None)
                LOGGER.warning(
                    "Could not send Minecraft lines to channel_id=%s",
                    channel_id,
                )

    async def _append_to_open(
        self,
        channel_id: int,
        pending: list[str],
    ) -> list[str]:
        """Fill the open terminal message; return the lines that did not fit."""
        entry = self._open.get(channel_id)

        if entry is None:
            return pending

        message, shown = entry
        combined = list(shown)
        index = 0

        while index < len(pending) and terminal_fits(combined + [pending[index]]):
            combined.append(pending[index])
            index += 1

        if index == 0:
            self._open.pop(channel_id, None)
            return pending

        try:
            await message.edit(content=render_terminal(combined))
        except discord.NotFound:
            # Alguien borró el mensaje: se empieza uno nuevo.
            self._open.pop(channel_id, None)
            return pending

        self._open[channel_id] = (message, combined)
        return pending[index:]

    def _split(self, lines: list[str]) -> list[list[str]]:
        groups: list[list[str]] = []
        current: list[str] = []

        for line in lines:
            if current and not terminal_fits(current + [line]):
                groups.append(current)
                current = []

            current.append(line)

        if current:
            groups.append(current)

        return groups


class MinecraftCog(commands.Cog):
    """Link Discord with the Minecraft server."""

    minecraft = app_commands.Group(
        name="minecraft",
        description="Servidor de Minecraft: estado, vinculación y economía.",
        guild_only=True,
    )

    minecraft_admin = app_commands.Group(
        name="minecraft_admin",
        description="Administra la integración con el servidor de Minecraft.",
        guild_only=True,
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        settings = bot.settings
        self.bridge_token = settings.minecraft_bridge_token

        self.bridge = MinecraftBridge(
            host=settings.minecraft_bridge_host,
            port=settings.minecraft_bridge_port,
            token=self.bridge_token,
        )

        self.repository = MinecraftRepository()
        self.guild_settings: dict[int, MinecraftGuildSettings] = {}

        self.chat_lines = LineBuffer(bot)
        self.console_lines = LineBuffer(bot)

        # Evita anunciar dos veces que el servidor se apagó.
        self.offline_announced = True
        # Últimos datos recibidos del servidor (nombre, versión, jugadores,
        # máximo y TPS); se conservan aunque se desconecte.
        self.server_info: dict[str, Any] = {}
        self.status_dirty = asyncio.Event()
        self.status_task: asyncio.Task[None] | None = None
        self.background_tasks: set[asyncio.Task[None]] = set()

    async def cog_load(self) -> None:
        """Start the bridge and the status updater."""
        self.repository.initialize()
        self._reload_settings()

        self.bridge.add_listener(self._on_bridge_event)

        if not self.bridge_token:
            LOGGER.warning(
                "MINECRAFT_BRIDGE_TOKEN is empty: the Minecraft bridge "
                "is disabled."
            )
        else:
            try:
                await self.bridge.start()
            except OSError:
                LOGGER.exception(
                    "Could not start the Minecraft bridge on %s:%s",
                    self.bridge.host,
                    self.bridge.port,
                )

        self.status_dirty.set()
        self.status_task = asyncio.create_task(self._status_loop())

    async def cog_unload(self) -> None:
        """Stop the bridge and pending tasks."""
        if self.status_task is not None:
            self.status_task.cancel()

        self.chat_lines.cancel()
        self.console_lines.cancel()

        await self.bridge.stop()

        # Sin Odinus nadie actualiza el estado: se deja en "apagado" para
        # que no se quede congelado mostrando el servidor en línea.
        try:
            await self._update_status_messages()
        except Exception:
            LOGGER.exception("Could not mark the Minecraft status as offline.")

    # ============================================================ helpers

    def _reload_settings(self) -> None:
        self.guild_settings = {
            settings.guild_id: settings
            for settings in self.repository.all_settings()
        }

    def _settings(self, guild_id: int) -> MinecraftGuildSettings:
        return self.guild_settings.get(
            guild_id,
            MinecraftGuildSettings(guild_id),
        )

    def _spawn(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    def _chat_line(self, line: str, exclude: int | None = None) -> None:
        stamped = f"{GRAY}[{now_text()}]{RESET} {line}"

        for settings in self.guild_settings.values():
            channel_id = settings.chat_channel_id

            if channel_id is not None and channel_id != exclude:
                self.chat_lines.add(channel_id, stamped)

    def _server_line(self, text: str) -> None:
        self._chat_line(f"{PINK}[SERVIDOR]{RESET} {text}")

    async def _request_with_retry(
        self,
        request_type: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a request, retrying once if the answer did not arrive.

        Only used for operations with an idempotency key, so a retry can
        never apply the same operation twice.
        """
        try:
            return await self.bridge.request(request_type, data)
        except BridgeUnavailable:
            await asyncio.sleep(2)
            return await self.bridge.request(request_type, data)

    async def _economy_channel_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        settings = self._settings(interaction.guild_id or 0)

        return await self._channel_check(
            interaction,
            settings.economy_channel_id,
            "💰 Los comandos de economía se usan en",
        )

    async def _link_channel_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        settings = self._settings(interaction.guild_id or 0)

        return await self._channel_check(
            interaction,
            settings.link_channel_id,
            "🔗 La vinculación de cuentas se hace en",
        )

    async def _channel_check(
        self,
        interaction: discord.Interaction,
        channel_id: int | None,
        text: str,
    ) -> bool:
        """Allow the command only in its configured channel, if any."""
        if channel_id is None or interaction.channel_id == channel_id:
            return True

        await interaction.response.send_message(
            f"{text} <#{channel_id}>.",
            ephemeral=True,
        )
        return False

    async def _require_link(
        self,
        interaction: discord.Interaction,
        member: discord.abc.User,
    ) -> MinecraftLink | None:
        link = self.repository.link_for_discord(member.id)

        if link is None:
            if member.id == interaction.user.id:
                text = (
                    "No tienes una cuenta de Minecraft vinculada. "
                    "Usa `/minecraft vincular`."
                )
            else:
                text = (
                    f"{member.mention} no tiene una cuenta de Minecraft "
                    "vinculada."
                )

            await interaction.followup.send(
                text,
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        return link

    def _status_embed(
        self,
        settings: MinecraftGuildSettings,
        players: list[dict[str, Any]] | None = None,
    ) -> discord.Embed:
        status = self.bridge.status or {}
        # Justo después del hello todavía no llega el primer status, pero
        # el hello ya trae los jugadores: el servidor se da por encendido.
        online = (
            self.bridge.connected
            and bool(status or self.bridge.hello)
            and status.get("online", True)
        )
        # Últimos datos conocidos, para mostrarlos también con el servidor
        # apagado.
        info = self.server_info
        server_name = discord.utils.escape_markdown(
            str(info.get("server", "Minecraft"))
        )
        max_players = info.get("max_players")
        max_text = str(max_players) if isinstance(max_players, int) else "—"

        if online:
            embed = discord.Embed(
                title="🟢 Servidor de Minecraft en línea",
                description=f"**{server_name}**",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow(),
            )
            players_text = f"{info.get('players', 0)}/{max_text}"
            tps = info.get("tps")
            tps_text = f"{tps:.1f}" if isinstance(tps, (int, float)) else "—"
        else:
            embed = discord.Embed(
                title="🔴 Servidor de Minecraft apagado",
                description=(
                    f"**{server_name}**\n"
                    "El servidor está apagado o sin conexión con Odinus."
                ),
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow(),
            )
            players_text = f"0/{max_text}"
            tps_text = "—"

        embed.add_field(name="👥 Jugadores", value=players_text, inline=True)
        embed.add_field(name="⚡ TPS", value=tps_text, inline=True)
        embed.add_field(
            name="🧩 Versión",
            value=str(info.get("minecraft_version", "—")),
            inline=True,
        )

        if online and players:
            names = ", ".join(
                discord.utils.escape_markdown(str(player.get("name", "?")))
                for player in players
            )
            embed.add_field(
                name="🎮 Conectados",
                value=names[:1024],
                inline=False,
            )

        # La dirección se muestra siempre, también con el servidor apagado,
        # para que la gente sepa dónde entrar cuando vuelva.
        if settings.java_address:
            embed.add_field(
                name="☕ Java",
                value=f"`{settings.java_address}`",
                inline=True,
            )

        if settings.bedrock_address:
            embed.add_field(
                name="📱 Bedrock",
                value=f"`{settings.bedrock_address}`",
                inline=True,
            )

        embed.set_footer(text="Odinus • Minecraft")
        return embed

    # ====================================================== bridge events

    async def _on_bridge_event(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Handle plugin events (runs inside the bridge read loop)."""
        name = clean_text(data.get("name", "?"), 32)

        if event_type in ("hello", "status"):
            self.server_info.update(
                {
                    key: data[key]
                    for key in (
                        "server",
                        "minecraft_version",
                        "players",
                        "max_players",
                        "tps",
                    )
                    if key in data
                }
            )

        if event_type == "hello":
            self.offline_announced = False
            self._server_line(
                f"Conectado · {clean_text(data.get('server', 'Minecraft'), 64)}"
                f" · Minecraft {clean_text(data.get('minecraft_version', '?'), 16)}"
            )
            self.status_dirty.set()

        elif event_type == "status":
            if data.get("online") is False and not self.offline_announced:
                self.offline_announced = True
                self._server_line("Apagado")

            self.status_dirty.set()

        elif event_type == "disconnected":
            if not self.offline_announced:
                self.offline_announced = True
                self._server_line("Conexión perdida: servidor apagado o caído")

            self.status_dirty.set()

        elif event_type == "chat":
            rank = data.get("rank")
            rank_text = (
                f"{YELLOW}[{clean_text(rank, 24)}]{RESET} "
                if rank and rank != "USER"
                else ""
            )
            self._chat_line(
                f"{rank_text}{CYAN}<{name}>{RESET} "
                f"{clean_text(data.get('message', ''), 300)}"
            )

        elif event_type == "join":
            text = (
                "entró por primera vez al servidor"
                if data.get("first_join")
                else "entró al servidor"
            )
            self._chat_line(f"{GREEN}[+] {name} {text}{RESET}")

        elif event_type == "quit":
            self._chat_line(f"{RED}[-] {name} salió del servidor{RESET}")

        elif event_type == "death":
            self._chat_line(
                f"{RED}[☠] {clean_text(data.get('message', name), 300)}{RESET}"
            )

        elif event_type == "advancement":
            self._chat_line(
                f"{YELLOW}[★] {name} consiguió el logro "
                f"\"{clean_text(data.get('title', '?'), 100)}\"{RESET}"
            )

        elif event_type == "console_line":
            self._console_lines(data)

        elif event_type == "link_confirmed":
            self._spawn(self._complete_link(data))

        elif event_type == "unlink_request":
            self._spawn(self._handle_unlink_request(data))

    def _console_lines(self, data: dict[str, Any]) -> None:
        lines = data.get("lines")

        if not isinstance(lines, list):
            return

        cleaned = [color_console_line(clean_text(line, 1000)) for line in lines]
        omitted = data.get("omitted")

        if isinstance(omitted, int) and omitted > 0:
            cleaned.append(f"{GRAY}… {omitted} línea(s) omitida(s){RESET}")

        for settings in self.guild_settings.values():
            if settings.console_channel_id is not None:
                for line in cleaned:
                    self.console_lines.add(settings.console_channel_id, line)

    async def _complete_link(self, data: dict[str, Any]) -> None:
        try:
            discord_id = int(data["discord_id"])
            player_uuid = str(data["uuid"])
            name = str(data["name"])
        except (KeyError, TypeError, ValueError):
            LOGGER.warning("Ignoring malformed link_confirmed event.")
            return

        previous = self.repository.link_for_discord(discord_id)
        self.repository.save_link(discord_id, player_uuid, name)

        LOGGER.info(
            "Linked discord_id=%s with Minecraft player %s (%s)",
            discord_id,
            name,
            player_uuid,
        )

        # Al vincular otra cuenta, la anterior deja de tener acceso.
        if previous is not None and previous.uuid != player_uuid:
            try:
                await self.bridge.request(
                    "link_remove",
                    {"uuid": previous.uuid},
                )
            except (BridgeError, BridgeUnavailable):
                LOGGER.warning(
                    "Could not remove the previous account %s from the "
                    "whitelist.",
                    previous.name,
                )

        await self._notify(
            discord_id,
            f"✅ Tu cuenta de Discord quedó vinculada con el jugador "
            f"**{discord.utils.escape_markdown(name)}** de Minecraft.",
        )

    async def _handle_unlink_request(self, data: dict[str, Any]) -> None:
        player_uuid = data.get("uuid")

        if not isinstance(player_uuid, str):
            return

        link = self.repository.delete_link_for_uuid(player_uuid)

        # El protocolo exige link_remove para sacarlo de la whitelist.
        try:
            await self.bridge.request("link_remove", {"uuid": player_uuid})
        except (BridgeError, BridgeUnavailable):
            LOGGER.warning(
                "Could not remove %s from the whitelist after /desvincular.",
                player_uuid,
            )

        if link is not None:
            await self._notify(
                link.discord_id,
                f"🔓 Tu cuenta de Discord se desvinculó del jugador "
                f"**{discord.utils.escape_markdown(link.name)}** "
                "desde el juego.",
            )

    async def _notify(self, user_id: int, text: str) -> None:
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(
                user_id
            )
            await user.send(text)
        except discord.HTTPException:
            pass

    # ====================================================== status message

    async def _status_loop(self) -> None:
        await self.bot.wait_until_ready()

        while True:
            await self.status_dirty.wait()
            self.status_dirty.clear()

            await self._update_status_messages()
            await asyncio.sleep(STATUS_EDIT_INTERVAL)

    async def _update_status_messages(self) -> None:
        for settings in list(self.guild_settings.values()):
            if settings.status_channel_id is None or settings.status_message_id is None:
                continue

            embed = self._status_embed(settings)

            channel = self.bot.get_channel(settings.status_channel_id)

            if not isinstance(channel, discord.TextChannel):
                continue

            try:
                await channel.get_partial_message(
                    settings.status_message_id
                ).edit(embed=embed)
            except discord.NotFound:
                LOGGER.warning(
                    "Minecraft status message was deleted guild_id=%s",
                    settings.guild_id,
                )
            except discord.HTTPException:
                LOGGER.warning(
                    "Could not update the Minecraft status message "
                    "guild_id=%s",
                    settings.guild_id,
                )

    # ===================================================== Discord → server

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Forward the chat channel and run commands from the console channel."""
        if message.guild is None:
            return

        settings = self._settings(message.guild.id)
        channel_id = message.channel.id

        if channel_id == settings.chat_channel_id:
            buffer = self.chat_lines
        elif channel_id == settings.console_channel_id:
            buffer = self.console_lines
        else:
            return

        # Los mensajes de terminal de Odinus no cuentan como interrupción.
        if self.bot.user is not None and message.author.id == self.bot.user.id:
            return

        if message.author.bot or message.webhook_id is not None:
            buffer.interrupt(channel_id)
            return

        if buffer is self.chat_lines:
            kept = await self._forward_chat(message)
        else:
            kept = await self._run_console_message(message)

        # Si el mensaje se queda en el canal, la terminal sigue debajo de él.
        if kept:
            buffer.interrupt(channel_id)

    async def _forward_chat(self, message: discord.Message) -> bool:
        """Send a Discord message to the game; return whether it stays."""
        text = message.clean_content.strip()

        if message.attachments:
            text = f"{text} [adjunto]".strip()

        if not text:
            return True

        name = (
            message.author.display_name
            if isinstance(message.author, discord.Member)
            else message.author.name
        )

        try:
            await self.bridge.request(
                "chat",
                {
                    "discord_id": str(message.author.id),
                    "name": name[:32],
                    "message": text[:4000],
                },
            )
        except (BridgeError, BridgeUnavailable):
            try:
                await message.add_reaction("❌")
            except discord.HTTPException:
                pass
            return True

        # Se borra el original y se vuelve a mostrar como línea de la
        # terminal, para que el canal se vea uniforme.
        kept = not await self._delete_quietly(message)

        if kept:
            try:
                await message.add_reaction("✅")
            except discord.HTTPException:
                pass

        self._chat_line(
            f"{BLUE}[Discord] {clean_text(name, 32)}:{RESET} "
            f"{clean_text(text, 300)}",
            exclude=message.channel.id if kept else None,
        )
        return kept

    async def _run_console_message(self, message: discord.Message) -> bool:
        """Run an administrator command; return whether the message stays."""
        if (
            not isinstance(message.author, discord.Member)
            or not message.author.guild_permissions.administrator
        ):
            return True

        command = message.content.strip()

        if not command:
            return True

        kept = not await self._delete_quietly(message)
        channel_id = message.channel.id

        # El comando y su respuesta se escriben en la misma terminal.
        self.console_lines.add(
            channel_id,
            f"{GREEN}> {clean_text(message.author.display_name, 32)}:{RESET} "
            f"{clean_text(command, 256)}",
        )

        try:
            data = await self.bridge.request(
                "console_command",
                {"command": command[:256]},
            )
        except (BridgeError, BridgeUnavailable) as error:
            self.console_lines.add(
                channel_id,
                f"{RED}{clean_text(describe_error(error), 300)}{RESET}",
            )
            return kept

        output = data.get("output")
        lines = output if isinstance(output, list) else []

        for line in lines:
            self.console_lines.add(channel_id, clean_text(line, 1000))

        if not lines:
            note = "(sin salida)" if data.get("success") else "(comando desconocido)"
            self.console_lines.add(channel_id, f"{GRAY}{note}{RESET}")

        return kept

    async def _delete_quietly(self, message: discord.Message) -> bool:
        """Delete a message; return whether it was deleted."""
        try:
            await message.delete()
        except discord.HTTPException:
            return False

        return True

    def _command_output(self, data: dict[str, Any]) -> str:
        output = data.get("output")
        lines = (
            [clean_text(line, 1000) for line in output]
            if isinstance(output, list)
            else []
        )
        icon = "✅" if data.get("success") else "⚠️"
        body = "\n".join(lines) or "(sin salida)"

        return f"{icon}\n```\n{body[:1900]}\n```"

    # ===================================================== user commands

    @minecraft.command(
        name="estado",
        description="Muestra el estado del servidor de Minecraft.",
    )
    async def estado(self, interaction: discord.Interaction) -> None:
        """Show whether the server is online and who is playing."""
        await interaction.response.defer()

        players: list[dict[str, Any]] | None = None

        if self.bridge.connected:
            try:
                data = await self.bridge.request("players_online")
                players = data.get("players")
            except (BridgeError, BridgeUnavailable):
                players = None

        await interaction.followup.send(
            embed=self._status_embed(
                self._settings(interaction.guild_id or 0),
                players,
            ),
        )

    @minecraft.command(
        name="vincular",
        description="Vincula tu cuenta de Discord con tu jugador de Minecraft.",
    )
    @app_commands.describe(
        nick="Tu nombre de jugador en Minecraft.",
    )
    async def vincular(
        self,
        interaction: discord.Interaction,
        nick: str,
    ) -> None:
        """Create a link code and whitelist the nick."""
        if not await self._link_channel_check(interaction):
            return

        nick = nick.strip()

        if not NICK_PATTERN.fullmatch(nick):
            await interaction.response.send_message(
                "❌ Ese nick no es válido. Solo puede tener letras, números, "
                "`_`, `.`, `*` o `-`, y hasta 20 caracteres.",
                ephemeral=True,
            )
            return

        current = self.repository.link_for_discord(interaction.user.id)

        if current is not None and current.name.lower() == nick.lower():
            await interaction.response.send_message(
                f"✅ Ya estás vinculado con **{discord.utils.escape_markdown(current.name)}**.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        code = "".join(
            secrets.choice(LINK_CODE_ALPHABET)
            for _ in range(LINK_CODE_LENGTH)
        )

        try:
            data = await self.bridge.request(
                "link_create",
                {
                    "code": code,
                    "discord_id": str(interaction.user.id),
                    "nick": nick,
                },
            )
        except (BridgeError, BridgeUnavailable) as error:
            await interaction.followup.send(
                describe_error(error),
                ephemeral=True,
            )
            return

        expires_at = data.get("expires_at")
        expires_text = (
            f"<t:{int(expires_at) // 1000}:R>"
            if isinstance(expires_at, int)
            else "en unos minutos"
        )

        embed = discord.Embed(
            title="🔗 Vinculación con Minecraft",
            description=(
                f"1. Entra al servidor con el nick "
                f"**{discord.utils.escape_markdown(nick)}**.\n"
                "2. Inicia sesión como siempre.\n"
                f"3. Escribe en el chat del juego:\n"
                f"# `/vincular {code}`\n"
                f"⏳ El código caduca {expires_text}."
            ),
            color=discord.Color.green(),
        )

        if current is not None:
            embed.add_field(
                name="⚠️ Ya tenías una cuenta vinculada",
                value=(
                    f"Al confirmar, **{discord.utils.escape_markdown(current.name)}** "
                    "dejará de estar vinculada y saldrá de la whitelist."
                ),
                inline=False,
            )

        embed.set_footer(text="Odinus • Minecraft")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @minecraft.command(
        name="desvincular",
        description="Desvincula tu cuenta de Minecraft de Discord.",
    )
    async def desvincular(self, interaction: discord.Interaction) -> None:
        """Remove the user's own link."""
        if not await self._link_channel_check(interaction):
            return

        await self._unlink(interaction, interaction.user)

    async def _unlink(
        self,
        interaction: discord.Interaction,
        member: discord.abc.User,
    ) -> None:
        link = self.repository.link_for_discord(member.id)

        if link is None:
            await interaction.response.send_message(
                "No hay ninguna cuenta de Minecraft vinculada.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Primero se saca de la whitelist; si el servidor no responde, el
        # vínculo se conserva para no dejar los dos lados distintos.
        try:
            await self.bridge.request("link_remove", {"uuid": link.uuid})
        except (BridgeError, BridgeUnavailable) as error:
            await interaction.followup.send(
                describe_error(error)
                + "\nInténtalo cuando el servidor esté encendido.",
                ephemeral=True,
            )
            return

        self.repository.delete_link_for_discord(member.id)

        await interaction.followup.send(
            f"🔓 Se desvinculó **{discord.utils.escape_markdown(link.name)}** "
            "y se quitó de la whitelist.",
            ephemeral=True,
        )

    @minecraft.command(
        name="perfil",
        description="Muestra el jugador, rango y dinero de un miembro.",
    )
    @app_commands.describe(
        usuario="Miembro a consultar (por defecto, tú).",
    )
    async def perfil(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member | None = None,
    ) -> None:
        """Combine link, ranks, balance and online state."""
        member = usuario or interaction.user

        await interaction.response.defer()

        link = await self._require_link(interaction, member)

        if link is None:
            return

        balance, ranks, online = await asyncio.gather(
            self.bridge.request("balance_get", {"uuid": link.uuid}),
            self.bridge.request("ranks_get", {"uuid": link.uuid}),
            self.bridge.request("players_online"),
            return_exceptions=True,
        )

        embed = discord.Embed(
            title=f"⛏️ {discord.utils.escape_markdown(link.name)}",
            description=f"Cuenta de Minecraft de {member.mention}",
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=skin_url(link.name))

        if isinstance(online, dict):
            is_online = any(
                player.get("uuid") == link.uuid
                for player in online.get("players", [])
            )
            embed.add_field(
                name="📡 Estado",
                value="🟢 Jugando ahora" if is_online else "⚫ Desconectado",
                inline=True,
            )
        else:
            embed.add_field(name="📡 Estado", value="🔴 Servidor apagado", inline=True)

        if isinstance(ranks, dict):
            embed.add_field(
                name="🎖️ Rango",
                value=f"**{ranks.get('primary', 'USER')}**",
                inline=True,
            )

        if isinstance(balance, dict):
            currency = balance.get("currency", "")
            embed.add_field(
                name="💰 Dinero",
                value=(
                    f"👛 Cartera: **{format_amount(balance.get('wallet', 0), currency)}**\n"
                    f"🏦 Banco: **{format_amount(balance.get('bank', 0), currency)}**\n"
                    f"💎 Total: **{format_amount(balance.get('total', 0), currency)}**"
                ),
                inline=False,
            )

        linked_at = datetime.fromisoformat(link.linked_at)
        embed.set_footer(text="Odinus • Minecraft · Vinculado")
        embed.timestamp = linked_at

        await interaction.followup.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @minecraft.command(
        name="saldo",
        description="Consulta la cartera y el banco de Minecraft.",
    )
    @app_commands.describe(
        usuario="Miembro a consultar (por defecto, tú).",
    )
    async def saldo(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member | None = None,
    ) -> None:
        """Show the wallet and bank of a linked member."""
        if not await self._economy_channel_check(interaction):
            return

        member = usuario or interaction.user

        await interaction.response.defer()

        link = await self._require_link(interaction, member)

        if link is None:
            return

        try:
            data = await self.bridge.request("balance_get", {"uuid": link.uuid})
        except (BridgeError, BridgeUnavailable) as error:
            await interaction.followup.send(describe_error(error))
            return

        currency = data.get("currency", "")

        embed = discord.Embed(
            title=f"💰 Saldo de {discord.utils.escape_markdown(link.name)}",
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=skin_url(link.name))
        embed.add_field(
            name="👛 Cartera",
            value=format_amount(data.get("wallet", 0), currency),
            inline=True,
        )
        embed.add_field(
            name="🏦 Banco",
            value=format_amount(data.get("bank", 0), currency),
            inline=True,
        )
        embed.add_field(
            name="💎 Total",
            value=f"**{format_amount(data.get('total', 0), currency)}**",
            inline=False,
        )
        embed.set_footer(text="Odinus • Odin Economy")

        await interaction.followup.send(embed=embed)

    @minecraft.command(
        name="top",
        description="Ranking de los jugadores con más dinero.",
    )
    async def top(self, interaction: discord.Interaction) -> None:
        """Show the richest players."""
        if not await self._economy_channel_check(interaction):
            return

        await interaction.response.defer()

        try:
            data = await self.bridge.request("economy_top", {"limit": 10})
        except (BridgeError, BridgeUnavailable) as error:
            await interaction.followup.send(describe_error(error))
            return

        currency = data.get("currency", "")
        entries = data.get("top", [])
        medals = ("🥇", "🥈", "🥉")

        lines = [
            f"{medals[index] if index < 3 else f'`#{index + 1}`'} "
            f"**{discord.utils.escape_markdown(str(entry.get('name', '?')))}** — "
            f"{format_amount(entry.get('total', 0), currency)}"
            for index, entry in enumerate(entries)
        ]

        embed = discord.Embed(
            title="🏆 Los más ricos del servidor",
            description="\n".join(lines) or "Todavía no hay cuentas.",
            color=discord.Color.gold(),
        )
        embed.set_footer(text="Odinus • Odin Economy · Cartera + banco")

        await interaction.followup.send(embed=embed)

    # ===================================================== admin commands

    @minecraft_admin.command(
        name="canal",
        description="Configura un canal de la integración con Minecraft.",
    )
    @app_commands.describe(
        tipo="Qué función tendrá el canal.",
        canal="Canal a usar. Déjalo vacío para quitar la configuración.",
    )
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Chat de Minecraft (público)", value="chat"),
            app_commands.Choice(name="Consola de admins (privado)", value="consola"),
            app_commands.Choice(name="Estado del servidor", value="estado"),
            app_commands.Choice(name="Economía", value="economia"),
            app_commands.Choice(name="Vinculación de cuentas", value="vinculacion"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def canal(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        canal: discord.TextChannel | None = None,
    ) -> None:
        """Set or clear one of the integration channels."""
        if interaction.guild is None:
            return

        guild = interaction.guild

        if canal is None:
            self.repository.set_channel(guild.id, tipo.value, None)
            self._reload_settings()

            await interaction.response.send_message(
                f"🗑️ Se quitó el canal de **{tipo.name}**.",
                ephemeral=True,
            )
            return

        me = guild.me
        permissions = canal.permissions_for(me)
        missing = []

        if not permissions.view_channel:
            missing.append("Ver canal")

        if not permissions.send_messages:
            missing.append("Enviar mensajes")

        if not permissions.embed_links:
            missing.append("Insertar enlaces")

        # En las terminales se borra lo que se escribe para mostrarlo
        # como una línea más.
        if tipo.value in ("chat", "consola") and not permissions.manage_messages:
            missing.append("Gestionar mensajes")

        if missing:
            await interaction.response.send_message(
                "No tengo los permisos necesarios en ese canal: "
                + ", ".join(missing)
                + ".",
                ephemeral=True,
            )
            return

        if (
            tipo.value == "consola"
            and canal.permissions_for(guild.default_role).view_channel
        ):
            await interaction.response.send_message(
                "🔒 La consola debe ser un canal **privado**: ahora mismo "
                "`@everyone` puede verlo. Quítale el permiso de ver el "
                "canal y vuelve a intentarlo.",
                ephemeral=True,
            )
            return

        previous = self._settings(guild.id)

        if tipo.value == "estado":
            try:
                message = await canal.send(
                    embed=self._status_embed(self._settings(guild.id))
                )
            except discord.HTTPException:
                await interaction.response.send_message(
                    "No pude publicar el mensaje de estado en ese canal.",
                    ephemeral=True,
                )
                return

            self.repository.set_status_message(guild.id, canal.id, message.id)
        else:
            self.repository.set_channel(guild.id, tipo.value, canal.id)

        self._reload_settings()
        settings = self._settings(guild.id)

        extra = ""

        # El mensaje de bienvenida solo se publica al estrenar el canal.
        intro = None

        if tipo.value == "economia" and previous.economy_channel_id != canal.id:
            intro = build_economy_intro_embed(settings)
        elif tipo.value == "vinculacion" and previous.link_channel_id != canal.id:
            intro = build_link_intro_embed(settings)

        if intro is not None:
            try:
                await canal.send(embed=intro)
            except discord.HTTPException:
                extra = "\n⚠️ No pude publicar el mensaje de bienvenida del canal."

        if tipo.value == "consola":
            extra = (
                "\nRecuerda activar `console.enabled: true` en la "
                "config de Odin-Discord. Lo que escriba un administrador "
                "aquí se ejecuta como comando del servidor."
            )
        elif tipo.value in ("economia", "vinculacion"):
            extra = (
                "\nLos comandos de este tema solo funcionarán en ese canal."
                + extra
            )
        elif tipo.value == "chat":
            extra = (
                "\nLo que se escriba aquí se enviará al chat del juego."
            )

        await interaction.response.send_message(
            f"✅ Canal de **{tipo.name}** configurado en {canal.mention}.{extra}",
            ephemeral=True,
        )

    @minecraft_admin.command(
        name="direccion",
        description="Configura la IP que se muestra para entrar al servidor.",
    )
    @app_commands.describe(
        java="Dirección para Java, por ejemplo: play.midominio.com o 1.2.3.4:25565",
        bedrock="Dirección para Bedrock, por ejemplo: play.midominio.com:19132",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def direccion(
        self,
        interaction: discord.Interaction,
        java: app_commands.Range[str, 1, 100] | None = None,
        bedrock: app_commands.Range[str, 1, 100] | None = None,
    ) -> None:
        """Set or clear the join addresses shown in the status message."""
        if interaction.guild is None:
            return

        addresses = [
            address.strip() if address else None
            for address in (java, bedrock)
        ]

        if any(address and ADDRESS_PATTERN.fullmatch(address) is None for address in addresses):
            await interaction.response.send_message(
                "❌ Dirección no válida. Usa solo el dominio o la IP y, si "
                "hace falta, el puerto: `play.midominio.com:25565`.",
                ephemeral=True,
            )
            return

        self.repository.set_addresses(interaction.guild.id, *addresses)
        self._reload_settings()
        self.status_dirty.set()

        java_address, bedrock_address = addresses

        if java_address is None and bedrock_address is None:
            text = (
                "🗑️ Se quitaron las direcciones: el mensaje de estado ya "
                "no mostrará la IP."
            )
        else:
            text = (
                "✅ Direcciones guardadas. Se mostrarán en el mensaje de "
                "estado y en `/minecraft estado`.\n"
                f"☕ Java: `{java_address or 'sin configurar'}`\n"
                f"📱 Bedrock: `{bedrock_address or 'sin configurar'}`"
            )

        await interaction.response.send_message(text, ephemeral=True)

    @minecraft_admin.command(
        name="depositar",
        description="Da dinero de Minecraft a un miembro vinculado.",
    )
    @app_commands.describe(
        usuario="Miembro que recibe el dinero.",
        cantidad="Cantidad a dar.",
        destino="Dónde se deposita.",
        motivo="Motivo que quedará en el historial.",
    )
    @app_commands.choices(
        destino=[
            app_commands.Choice(name="Cartera", value="wallet"),
            app_commands.Choice(name="Banco", value="bank"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def depositar(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        cantidad: app_commands.Range[int, 1, MAX_AMOUNT],
        destino: app_commands.Choice[str],
        motivo: app_commands.Range[str, 1, 120] = "Depósito desde Discord",
    ) -> None:
        """Give money to a linked member."""
        await self._move_money(
            interaction,
            "economy_deposit",
            usuario,
            cantidad,
            destino,
            motivo,
        )

    @minecraft_admin.command(
        name="retirar",
        description="Quita dinero de Minecraft a un miembro vinculado.",
    )
    @app_commands.describe(
        usuario="Miembro al que se le quita el dinero.",
        cantidad="Cantidad a quitar.",
        destino="De dónde se retira.",
        motivo="Motivo que quedará en el historial.",
    )
    @app_commands.choices(
        destino=[
            app_commands.Choice(name="Cartera", value="wallet"),
            app_commands.Choice(name="Banco", value="bank"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def retirar(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        cantidad: app_commands.Range[int, 1, MAX_AMOUNT],
        destino: app_commands.Choice[str],
        motivo: app_commands.Range[str, 1, 120] = "Retiro desde Discord",
    ) -> None:
        """Take money from a linked member."""
        await self._move_money(
            interaction,
            "economy_withdraw",
            usuario,
            cantidad,
            destino,
            motivo,
        )

    async def _move_money(
        self,
        interaction: discord.Interaction,
        request_type: str,
        member: discord.Member,
        amount: int,
        target: app_commands.Choice[str],
        reason: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        link = await self._require_link(interaction, member)

        if link is None:
            return

        try:
            data = await self._request_with_retry(
                request_type,
                {
                    "uuid": link.uuid,
                    "amount": amount,
                    "target": target.value,
                    "reason": f"{reason} (por {interaction.user.name})",
                    # Una clave por comando: si se reintenta, no se repite.
                    "idempotency_key": f"odinus-{interaction.id}",
                },
            )
        except BridgeUnavailable:
            await interaction.followup.send(
                OFFLINE_MESSAGE
                + "\nNo se pudo confirmar la operación: revisa el saldo "
                "con `/minecraft saldo` antes de repetirla.",
                ephemeral=True,
            )
            return
        except BridgeError as error:
            await interaction.followup.send(describe_error(error), ephemeral=True)
            return

        currency = data.get("currency", "")
        verb = "Se dieron" if request_type == "economy_deposit" else "Se quitaron"
        place = "la cartera" if target.value == "wallet" else "el banco"

        LOGGER.info(
            "%s %s %s to/from %s (%s) by user_id=%s",
            request_type,
            amount,
            target.value,
            link.name,
            link.uuid,
            interaction.user.id,
        )

        await interaction.followup.send(
            f"✅ {verb} **{format_amount(amount, currency)}** en {place} de "
            f"**{discord.utils.escape_markdown(link.name)}**.\n"
            f"👛 Cartera: {format_amount(data.get('wallet', 0), currency)} · "
            f"🏦 Banco: {format_amount(data.get('bank', 0), currency)}",
            ephemeral=True,
        )

    @minecraft_admin.command(
        name="whitelist",
        description="Añade o quita un nick de la whitelist del servidor.",
    )
    @app_commands.describe(
        accion="Añadir o quitar.",
        nick="Nombre del jugador.",
    )
    @app_commands.choices(
        accion=[
            app_commands.Choice(name="Añadir", value="whitelist_add"),
            app_commands.Choice(name="Quitar", value="whitelist_remove"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist(
        self,
        interaction: discord.Interaction,
        accion: app_commands.Choice[str],
        nick: str,
    ) -> None:
        """Edit the server whitelist without linking."""
        nick = nick.strip()

        if not NICK_PATTERN.fullmatch(nick):
            await interaction.response.send_message(
                "❌ Ese nick no es válido.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            data = await self.bridge.request(accion.value, {"nick": nick})
        except (BridgeError, BridgeUnavailable) as error:
            await interaction.followup.send(describe_error(error), ephemeral=True)
            return

        safe_nick = discord.utils.escape_markdown(nick)

        if accion.value == "whitelist_add":
            text = f"✅ **{safe_nick}** se añadió a la whitelist."
        else:
            text = (
                f"🗑️ **{safe_nick}** se quitó de la whitelist "
                f"({data.get('removed', 0)} entrada(s))."
            )

        await interaction.followup.send(text, ephemeral=True)

    @minecraft_admin.command(
        name="desvincular",
        description="Quita el vínculo de Minecraft de un miembro.",
    )
    @app_commands.describe(
        usuario="Miembro a desvincular.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_desvincular(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
    ) -> None:
        """Remove another member's link."""
        await self._unlink(interaction, usuario)

    @minecraft_admin.command(
        name="comando",
        description="Ejecuta un comando en la consola del servidor.",
    )
    @app_commands.describe(
        comando="Comando sin la barra, por ejemplo: list",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def comando(
        self,
        interaction: discord.Interaction,
        comando: app_commands.Range[str, 1, 256],
    ) -> None:
        """Run a console command and show its output."""
        await interaction.response.defer(ephemeral=True)

        try:
            data = await self.bridge.request(
                "console_command",
                {"command": comando},
            )
        except (BridgeError, BridgeUnavailable) as error:
            await interaction.followup.send(describe_error(error), ephemeral=True)
            return

        await interaction.followup.send(
            self._command_output(data),
            ephemeral=True,
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Explain failed administrator checks privately."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "No tienes permiso para administrar la integración "
                "con Minecraft.",
                ephemeral=True,
            )
            return

        raise error


async def setup(bot: commands.Bot) -> None:
    """Register the Minecraft integration."""
    await bot.add_cog(MinecraftCog(bot))
