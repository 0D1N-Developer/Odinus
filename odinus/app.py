"""Discord application lifecycle and extension loading."""

import asyncio
import logging

import discord
from discord.ext import commands

from odinus.config import load_settings
from odinus.logging_config import configure_logging


LOGGER = logging.getLogger(__name__)


class OdinusBot(commands.Bot):
    """Bot container responsible for loading command modules."""

    async def setup_hook(self) -> None:
        await self.load_extension("odinus.cogs.general")
        await self.load_extension("odinus.cogs.cumpleanos")
        await self.load_extension("odinus.cogs.invitaciones")
        await self.load_extension("odinus.cogs.publicar")
        await self.load_extension("odinus.cogs.redes")
        await self.load_extension("odinus.cogs.paises")
        await self.load_extension("odinus.cogs.edad")
        await self.load_extension("odinus.cogs.niveles")
        await self.load_extension("odinus.cogs.recompensas")
        await self.load_extension("odinus.cogs.perfil")
        await self.load_extension("odinus.cogs.anuncios")

        synced_commands = await self.tree.sync()

        LOGGER.info(
            "Synchronized %s application command(s).",
            len(synced_commands),
        )


def create_bot() -> OdinusBot:
    """Build the bot with the intents needed by this version."""
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True

    return OdinusBot(
        command_prefix="!",
        intents=intents,
    )


def run() -> None:
    """Start Odinus using validated local settings."""
    configure_logging()

    settings = load_settings()
    bot = create_bot()

    try:
        bot.run(
            settings.discord_token,
            log_handler=None,
        )
    except KeyboardInterrupt:
        LOGGER.info("Odinus stopped by user.")
    except asyncio.CancelledError:
        LOGGER.info("Odinus shutdown was cancelled.")