"""Moderation commands and automatic moderation for Odinus."""

from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from datetime import timedelta
from time import monotonic

import discord
from discord import app_commands
from discord.ext import commands

from odinus.services.moderacion import ModerationRepository
from odinus.services.moderacion import ModerationService
from odinus.services.moderacion import contains_discord_invite
from odinus.services.moderacion import contains_suspicious_link
from odinus.ui.moderacion import ModeracionPanelView


LOGGER = logging.getLogger(__name__)


ACTION_NAMES = {
    "delete": "Eliminar mensaje",
    "warn": "Advertencia",
    "timeout": "Timeout",
}


AUTOMOD_RULE_NAMES = {
    "flood": "Anti-flood",
    "repeated_chars": "Caracteres repetidos",
    "repeated_questions": "Signos ? repetidos",
    "repeated_exclamations": "Signos ! repetidos",
    "discord_invites": "Invitaciones de Discord",
    "suspicious_links": "Enlaces sospechosos",
    "mention_spam": "Spam de menciones",
    "everyone_spam": "Spam de @everyone/@here",
    "emoji_spam": "Spam de emojis",
    "blocked_words": "Palabras bloqueadas",
}


AUTOMOD_RULES = tuple(
    AUTOMOD_RULE_NAMES.keys()
)


AUTOMOD_ACTIONS = {
    "delete": "Eliminar mensaje",
    "warn": "Advertencia",
    "timeout": "Timeout",
}


class ModeracionGroup(app_commands.Group):
    """Slash command group for moderation."""

    def __init__(
        self,
        repository: ModerationRepository,
        service: ModerationService,
    ) -> None:
        super().__init__(
            name="moderacion",
            description=(
                "Configura y administra la moderación del servidor."
            ),
        )

        self.repository = repository
        self.service = service

        self.message_history: dict[
            tuple[int, int, str],
            deque[float],
        ] = defaultdict(deque)

        self.mention_history: dict[
            tuple[int, int, str, int],
            deque[float],
        ] = defaultdict(deque)

        self.everyone_history: dict[
            tuple[int, int],
            deque[float],
        ] = defaultdict(deque)

        self.automod_cooldowns: dict[
            tuple[int, int, str],
            float,
        ] = {}

        self.bot: commands.Bot | None = None

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    async def _send_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
    ) -> None:
        settings = self.repository.get_settings(
            guild.id
        )

        if not settings.log_channel_id:
            return

        channel = guild.get_channel(
            settings.log_channel_id
        )

        if channel is None:
            return

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            return

        try:
            await channel.send(
                embed=embed
            )
        except discord.HTTPException:
            LOGGER.exception(
                "Could not send moderation log in guild %s.",
                guild.id,
            )

    async def _send_automod_log(
        self,
        message: discord.Message,
        rule: str,
        action: str,
    ) -> None:
        if message.guild is None:
            return

        embed = discord.Embed(
            title="AutoMod",
            color=discord.Color.orange(),
        )

        embed.add_field(
            name="Usuario",
            value=(
                f"{message.author.mention} "
                f"(`{message.author.id}`)"
            ),
            inline=False,
        )

        embed.add_field(
            name="Regla",
            value=AUTOMOD_RULE_NAMES.get(
                rule,
                rule,
            ),
            inline=True,
        )

        embed.add_field(
            name="Acción",
            value=ACTION_NAMES.get(
                action,
                action,
            ),
            inline=True,
        )

        embed.add_field(
            name="Canal",
            value=message.channel.mention,
            inline=True,
        )

        content = message.content.strip()

        if content:
            if len(content) > 1000:
                content = content[:997] + "..."

            embed.add_field(
                name="Mensaje",
                value=f"```{content}```",
                inline=False,
            )

        await self._send_log(
            message.guild,
            embed,
        )

    def _format_duration(
        self,
        seconds: int,
    ) -> str:
        if seconds < 60:
            return f"{seconds} segundos"

        minutes = seconds // 60

        if minutes < 60:
            return f"{minutes} minutos"

        hours = minutes // 60

        if hours < 24:
            return f"{hours} horas"

        days = hours // 24

        return f"{days} días"

    def _parse_duration(
        self,
        value: str,
    ) -> int | None:
        value = value.strip().lower()

        match = re.fullmatch(
            r"(\d+)\s*(s|m|h|d)",
            value,
        )

        if not match:
            return None

        amount = int(
            match.group(1)
        )

        unit = match.group(2)

        multipliers = {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400,
        }

        seconds = (
            amount
            * multipliers[unit]
        )

        if (
            seconds <= 0
            or seconds > 28 * 86400
        ):
            return None

        return seconds

    def _can_moderate(
        self,
        moderator: discord.Member,
        target: discord.Member,
    ) -> bool:
        if target.id == moderator.id:
            return False

        if target.id == moderator.guild.owner_id:
            return False

        if moderator.id != moderator.guild.owner_id:
            if target.top_role >= moderator.top_role:
                return False

        me = moderator.guild.me

        if me is not None:
            if target.top_role >= me.top_role:
                return False

        return True

    def _normalize_message(
        self,
        content: str,
    ) -> str:
        return " ".join(
            content.lower().split()
        )

    def _trim_history(
        self,
        history: deque[float],
        now: float,
        window_seconds: int,
    ) -> None:
        if window_seconds <= 0:
            window_seconds = 60

        while (
            history
            and now - history[0] > window_seconds
        ):
            history.popleft()

    def _emoji_count(
        self,
        content: str,
    ) -> int:
        count = 0

        for character in content:
            codepoint = ord(character)

            if (
                0x1F300 <= codepoint <= 0x1FAFF
                or 0x2600 <= codepoint <= 0x27BF
            ):
                count += 1

        return count

    def _is_on_cooldown(
        self,
        guild_id: int,
        user_id: int,
        rule: str,
    ) -> bool:
        key = (
            guild_id,
            user_id,
            rule,
        )

        now = monotonic()

        last = self.automod_cooldowns.get(
            key
        )

        if (
            last is not None
            and now - last < 10
        ):
            return True

        self.automod_cooldowns[key] = now

        return False

    async def _apply_automod_action(
        self,
        message: discord.Message,
        rule: str,
        action: str,
        timeout_seconds: int,
    ) -> None:
        guild = message.guild

        if guild is None:
            return

        if self._is_on_cooldown(
            guild.id,
            message.author.id,
            rule,
        ):
            return

        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            LOGGER.warning(
                "No permission to delete AutoMod message in guild %s.",
                guild.id,
            )
        except discord.HTTPException:
            LOGGER.exception(
                "Error deleting AutoMod message in guild %s.",
                guild.id,
            )

        bot_id = self.bot_user_id(
            guild
        )

        if action == "warn":
            self.service.add_warning(
                guild.id,
                message.author.id,
                bot_id,
                (
                    "AutoMod: "
                    f"{AUTOMOD_RULE_NAMES.get(rule, rule)}"
                ),
            )

        elif action == "timeout":
            member = guild.get_member(
                message.author.id
            )

            if member is not None:
                me = guild.me

                if (
                    me is not None
                    and member.top_role < me.top_role
                ):
                    try:
                        duration = min(
                            timeout_seconds,
                            28 * 86400,
                        )

                        await member.timeout(
                            timedelta(
                                seconds=duration
                            ),
                            reason=(
                                "AutoMod: "
                                f"{AUTOMOD_RULE_NAMES.get(rule, rule)}"
                            ),
                        )
                    except discord.HTTPException:
                        LOGGER.exception(
                            "Could not timeout AutoMod user %s.",
                            member.id,
                        )

        self.service.register_action(
            guild.id,
            message.author.id,
            bot_id,
            f"automod_{rule}",
            AUTOMOD_RULE_NAMES.get(
                rule,
                rule,
            ),
            timeout_seconds
            if action == "timeout"
            else None,
        )

        await self._send_automod_log(
            message,
            rule,
            action,
        )

    def bot_user_id(
        self,
        guild: discord.Guild,
    ) -> int:
        me = guild.me

        if me is not None:
            return me.id

        return 0

    # -----------------------------------------------------------------------
    # Message processing
    # -----------------------------------------------------------------------

    async def process_message(
        self,
        message: discord.Message,
    ) -> None:
        if message.guild is None:
            return

        if message.author.bot:
            return

        if self.service.is_ignored(
            message
        ):
            return

        await self._check_message_rules(
            message
        )

    async def _check_message_rules(
        self,
        message: discord.Message,
    ) -> None:
        guild = message.guild

        if guild is None:
            return

        self.repository.ensure_default_automod_rules(
            guild.id
        )

        rules = {
            rule.rule: rule
            for rule in self.repository.get_automod_rules(
                guild.id
            )
            if rule.enabled
        }

        # ---------------------------------------------------------------
        # Discord invites
        # ---------------------------------------------------------------

        invite_rule = rules.get(
            "discord_invites"
        )

        if (
            invite_rule
            and contains_discord_invite(
                message.content
            )
        ):
            await self._apply_automod_action(
                message,
                "discord_invites",
                invite_rule.action,
                invite_rule.timeout_seconds,
            )
            return

        # ---------------------------------------------------------------
        # Suspicious links
        # ---------------------------------------------------------------

        link_rule = rules.get(
            "suspicious_links"
        )

        if (
            link_rule
            and contains_suspicious_link(
                message.content
            )
        ):
            await self._apply_automod_action(
                message,
                "suspicious_links",
                link_rule.action,
                link_rule.timeout_seconds,
            )
            return

        # ---------------------------------------------------------------
        # Repeated characters
        # ---------------------------------------------------------------

        repeated_chars_rule = rules.get(
            "repeated_chars"
        )

        if repeated_chars_rule:
            threshold = max(
                1,
                repeated_chars_rule.threshold,
            )

            pattern = (
                rf"(.)\1{{{threshold - 1},}}"
            )

            if re.search(
                pattern,
                message.content,
                re.DOTALL,
            ):
                await self._apply_automod_action(
                    message,
                    "repeated_chars",
                    repeated_chars_rule.action,
                    repeated_chars_rule.timeout_seconds,
                )
                return

        # ---------------------------------------------------------------
        # Repeated question marks
        # ---------------------------------------------------------------

        question_rule = rules.get(
            "repeated_questions"
        )

        if question_rule:
            threshold = max(
                1,
                question_rule.threshold,
            )

            if re.search(
                rf"\?{{{threshold},}}",
                message.content,
            ):
                await self._apply_automod_action(
                    message,
                    "repeated_questions",
                    question_rule.action,
                    question_rule.timeout_seconds,
                )
                return

        # ---------------------------------------------------------------
        # Repeated exclamation marks
        # ---------------------------------------------------------------

        exclamation_rule = rules.get(
            "repeated_exclamations"
        )

        if exclamation_rule:
            threshold = max(
                1,
                exclamation_rule.threshold,
            )

            if re.search(
                rf"!{{{threshold},}}",
                message.content,
            ):
                await self._apply_automod_action(
                    message,
                    "repeated_exclamations",
                    exclamation_rule.action,
                    exclamation_rule.timeout_seconds,
                )
                return

        # ---------------------------------------------------------------
        # Emoji spam
        # ---------------------------------------------------------------

        emoji_rule = rules.get(
            "emoji_spam"
        )

        if emoji_rule:
            if (
                self._emoji_count(
                    message.content
                )
                >= emoji_rule.threshold
            ):
                await self._apply_automod_action(
                    message,
                    "emoji_spam",
                    emoji_rule.action,
                    emoji_rule.timeout_seconds,
                )
                return

        now = monotonic()

        # ---------------------------------------------------------------
        # Mention spam
        # ---------------------------------------------------------------

        mention_rule = rules.get(
            "mention_spam"
        )

        if mention_rule:
            targets = set()

            for user in message.mentions:
                targets.add(
                    (
                        "user",
                        user.id,
                    )
                )

            for role in message.role_mentions:
                targets.add(
                    (
                        "role",
                        role.id,
                    )
                )

            for target_type, target_id in targets:
                key = (
                    guild.id,
                    message.author.id,
                    target_type,
                    target_id,
                )

                history = self.mention_history[
                    key
                ]

                history.append(
                    now
                )

                self._trim_history(
                    history,
                    now,
                    mention_rule.window_seconds,
                )

                if (
                    len(history)
                    >= mention_rule.threshold
                ):
                    await self._apply_automod_action(
                        message,
                        "mention_spam",
                        mention_rule.action,
                        mention_rule.timeout_seconds,
                    )
                    return

        # ---------------------------------------------------------------
        # @everyone / @here spam
        # ---------------------------------------------------------------

        everyone_rule = rules.get(
            "everyone_spam"
        )

        if (
            everyone_rule
            and (
                message.mention_everyone
                or "@everyone" in message.content.lower()
                or "@here" in message.content.lower()
            )
        ):
            key = (
                guild.id,
                message.author.id,
            )

            history = self.everyone_history[
                key
            ]

            history.append(
                now
            )

            self._trim_history(
                history,
                now,
                everyone_rule.window_seconds,
            )

            if (
                len(history)
                >= everyone_rule.threshold
            ):
                await self._apply_automod_action(
                    message,
                    "everyone_spam",
                    everyone_rule.action,
                    everyone_rule.timeout_seconds,
                )
                return

        # ---------------------------------------------------------------
        # Anti-flood
        # ---------------------------------------------------------------

        flood_rule = rules.get(
            "flood"
        )

        if flood_rule:
            normalized = self._normalize_message(
                message.content
            )

            if normalized:
                key = (
                    guild.id,
                    message.author.id,
                    normalized,
                )

                history = self.message_history[
                    key
                ]

                history.append(
                    now
                )

                self._trim_history(
                    history,
                    now,
                    flood_rule.window_seconds,
                )

                if (
                    len(history)
                    >= flood_rule.threshold
                ):
                    await self._apply_automod_action(
                        message,
                        "flood",
                        flood_rule.action,
                        flood_rule.timeout_seconds,
                    )
                    return

        # ---------------------------------------------------------------
        # Blocked words
        # ---------------------------------------------------------------

        blocked_rule = rules.get(
            "blocked_words"
        )

        if blocked_rule:
            content_lower = (
                message.content.lower()
            )

            blocked_words = (
                self.repository.get_blocked_words(
                    guild.id
                )
            )

            for word in blocked_words:
                if (
                    word
                    and word in content_lower
                ):
                    await self._apply_automod_action(
                        message,
                        "blocked_words",
                        blocked_rule.action,
                        blocked_rule.timeout_seconds,
                    )
                    return

    # -----------------------------------------------------------------------
    # /moderacion panel
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="panel",
        description="Abre el panel interactivo de moderación.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def panel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando solo puede utilizarse dentro de un servidor.",
                ephemeral=True,
            )
            return

        self.repository.ensure_default_automod_rules(
            interaction.guild.id
        )

        embed = __import__(
            "odinus.ui.moderacion",
            fromlist=["build_main_embed"],
        ).build_main_embed(
            self.repository,
            interaction.guild,
        )

        await interaction.response.send_message(
            embed=embed,
            view=ModeracionPanelView(
                self.repository,
                interaction.guild.id,
            ),
            ephemeral=True,
        )

    # -----------------------------------------------------------------------
    # /moderacion configurar
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="configurar",
        description="Configura y activa la moderación.",
    )
    @app_commands.describe(
        canal_logs="Canal privado donde se enviarán los registros.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def configurar(
        self,
        interaction: discord.Interaction,
        canal_logs: discord.TextChannel,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando solo puede utilizarse dentro de un servidor.",
                ephemeral=True,
            )
            return

        self.repository.ensure_default_automod_rules(
            interaction.guild.id
        )

        self.repository.configure(
            interaction.guild.id,
            log_channel_id=canal_logs.id,
            enabled=True,
        )

        embed = discord.Embed(
            title="Moderación configurada",
            description=(
                "La moderación de Odinus está ahora **activa**."
            ),
            color=discord.Color.green(),
        )

        embed.add_field(
            name="Canal de registros",
            value=canal_logs.mention,
            inline=False,
        )

        embed.add_field(
            name="Estado",
            value="🟢 Activa",
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

        log_embed = discord.Embed(
            title="Moderación activada",
            description=(
                f"Configurada por {interaction.user.mention}."
            ),
            color=discord.Color.green(),
        )

        await self._send_log(
            interaction.guild,
            log_embed,
        )

    # -----------------------------------------------------------------------
    # /moderacion canal
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="canal",
        description="Cambia el canal de registros de moderación.",
    )
    @app_commands.describe(
        canal="Nuevo canal de registros.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def canal(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        if interaction.guild is None:
            return

        self.repository.set_log_channel(
            interaction.guild.id,
            canal.id,
        )

        await interaction.response.send_message(
            f"El canal de registros ahora es {canal.mention}.",
            ephemeral=True,
        )

    # -----------------------------------------------------------------------
    # Ignored channels
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="ignorar_canal",
        description="Ignora un canal en la moderación automática.",
    )
    @app_commands.describe(
        canal="Canal que será ignorado.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def ignorar_canal(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        if interaction.guild is None:
            return

        self.repository.add_ignored_channel(
            interaction.guild.id,
            canal.id,
        )

        await interaction.response.send_message(
            f"{canal.mention} ahora está ignorado por la moderación.",
            ephemeral=True,
        )

    @app_commands.command(
        name="quitar_canal",
        description="Quita un canal de la lista de ignorados.",
    )
    @app_commands.describe(
        canal="Canal que dejará de ser ignorado.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def quitar_canal(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        if interaction.guild is None:
            return

        self.repository.remove_ignored_channel(
            interaction.guild.id,
            canal.id,
        )

        await interaction.response.send_message(
            f"{canal.mention} ya no está ignorado.",
            ephemeral=True,
        )

    # -----------------------------------------------------------------------
    # Ignored roles
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="ignorar_rol",
        description="Ignora un rol en la moderación automática.",
    )
    @app_commands.describe(
        rol="Rol que será ignorado.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def ignorar_rol(
        self,
        interaction: discord.Interaction,
        rol: discord.Role,
    ) -> None:
        if interaction.guild is None:
            return

        self.repository.add_ignored_role(
            interaction.guild.id,
            rol.id,
        )

        await interaction.response.send_message(
            f"El rol {rol.mention} ahora está ignorado.",
            ephemeral=True,
        )

    @app_commands.command(
        name="quitar_rol",
        description="Quita un rol de la lista de ignorados.",
    )
    @app_commands.describe(
        rol="Rol que dejará de ser ignorado.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def quitar_rol(
        self,
        interaction: discord.Interaction,
        rol: discord.Role,
    ) -> None:
        if interaction.guild is None:
            return

        self.repository.remove_ignored_role(
            interaction.guild.id,
            rol.id,
        )

        await interaction.response.send_message(
            f"El rol {rol.mention} ya no está ignorado.",
            ephemeral=True,
        )

    # -----------------------------------------------------------------------
    # Estado
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="estado",
        description="Muestra el estado actual de la moderación.",
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def estado(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            return

        self.repository.ensure_default_automod_rules(
            interaction.guild.id
        )

        settings = self.repository.get_settings(
            interaction.guild.id
        )

        ignored_channels = (
            self.repository.get_ignored_channels(
                interaction.guild.id
            )
        )

        ignored_roles = (
            self.repository.get_ignored_roles(
                interaction.guild.id
            )
        )

        rules = self.repository.get_automod_rules(
            interaction.guild.id
        )

        embed = discord.Embed(
            title="Estado de moderación",
            color=(
                discord.Color.green()
                if settings.enabled
                else discord.Color.red()
            ),
        )

        embed.add_field(
            name="Estado",
            value=(
                "🟢 Activa"
                if settings.enabled
                else "🔴 Inactiva"
            ),
            inline=True,
        )

        if settings.log_channel_id:
            log_channel = interaction.guild.get_channel(
                settings.log_channel_id
            )

            log_value = (
                log_channel.mention
                if log_channel
                else f"<#{settings.log_channel_id}>"
            )
        else:
            log_value = "No configurado"

        embed.add_field(
            name="Registros",
            value=log_value,
            inline=True,
        )

        embed.add_field(
            name="Canales ignorados",
            value=str(
                len(ignored_channels)
            ),
            inline=True,
        )

        embed.add_field(
            name="Roles ignorados",
            value=str(
                len(ignored_roles)
            ),
            inline=True,
        )

        rules_text = []

        for rule in rules:
            status = (
                "🟢"
                if rule.enabled
                else "🔴"
            )

            if rule.window_seconds > 0:
                limits = (
                    f"{rule.threshold} / "
                    f"{rule.window_seconds}s"
                )
            else:
                limits = str(
                    rule.threshold
                )

            rules_text.append(
                f"{status} **"
                f"{AUTOMOD_RULE_NAMES.get(rule.rule, rule.rule)}"
                f"** — "
                f"{ACTION_NAMES.get(rule.action, rule.action)} — "
                f"`{limits}`"
            )

        embed.add_field(
            name="AutoMod",
            value="\n".join(
                rules_text
            ),
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    # -----------------------------------------------------------------------
    # Warn
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="warn",
        description="Advierte a un usuario.",
    )
    @app_commands.describe(
        usuario="Usuario que recibirá la advertencia.",
        razon="Motivo de la advertencia.",
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def warn(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        razon: str = "Sin razón especificada",
    ) -> None:
        if interaction.guild is None:
            return

        moderator = interaction.user

        if not isinstance(
            moderator,
            discord.Member,
        ):
            return

        if not self._can_moderate(
            moderator,
            usuario,
        ):
            await interaction.response.send_message(
                "No puedes moderar a ese usuario por la jerarquía de roles.",
                ephemeral=True,
            )
            return

        warning_id = self.service.add_warning(
            interaction.guild.id,
            usuario.id,
            moderator.id,
            razon,
        )

        self.service.register_action(
            interaction.guild.id,
            usuario.id,
            moderator.id,
            "warn",
            razon,
        )

        await interaction.response.send_message(
            f"⚠️ {usuario.mention} recibió una advertencia.\n"
            f"**Razón:** {razon}",
            ephemeral=True,
        )

        try:
            await usuario.send(
                f"Has recibido una advertencia en "
                f"**{interaction.guild.name}**.\n"
                f"Razón: {razon}"
            )
        except discord.HTTPException:
            pass

        embed = discord.Embed(
            title="Advertencia",
            color=discord.Color.yellow(),
        )

        embed.add_field(
            name="Usuario",
            value=(
                f"{usuario.mention} "
                f"(`{usuario.id}`)"
            ),
            inline=False,
        )

        embed.add_field(
            name="Moderador",
            value=moderator.mention,
            inline=True,
        )

        embed.add_field(
            name="Razón",
            value=razon,
            inline=False,
        )

        embed.set_footer(
            text=f"Advertencia #{warning_id}"
        )

        await self._send_log(
            interaction.guild,
            embed,
        )

    # -----------------------------------------------------------------------
    # Warnings
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="warnings",
        description="Muestra las advertencias de un usuario.",
    )
    @app_commands.describe(
        usuario="Usuario que quieres consultar.",
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def warnings(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
    ) -> None:
        if interaction.guild is None:
            return

        warnings = self.repository.get_warnings(
            interaction.guild.id,
            usuario.id,
        )

        if not warnings:
            await interaction.response.send_message(
                f"{usuario.mention} no tiene advertencias.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"Advertencias de {usuario}",
            color=discord.Color.yellow(),
        )

        lines = []

        for warning in warnings[:10]:
            moderator = interaction.guild.get_member(
                warning["moderator_id"]
            )

            moderator_name = (
                moderator.mention
                if moderator
                else f"<@{warning['moderator_id']}>"
            )

            lines.append(
                f"**#{warning['id']}** — "
                f"{warning['reason']}\n"
                f"Moderador: {moderator_name}\n"
                f"`{warning['created_at']}`"
            )

        embed.description = "\n\n".join(
            lines
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    # -----------------------------------------------------------------------
    # Modlogs
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="modlogs",
        description="Muestra el historial de moderación.",
    )
    @app_commands.describe(
        usuario="Usuario opcional.",
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def modlogs(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member | None = None,
    ) -> None:
        if interaction.guild is None:
            return

        actions = self.repository.get_actions(
            interaction.guild.id,
            usuario.id
            if usuario
            else None,
            limit=20,
        )

        if not actions:
            await interaction.response.send_message(
                "No hay registros de moderación.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Registros de moderación",
            color=discord.Color.blurple(),
        )

        lines = []

        for action in actions:
            target = interaction.guild.get_member(
                action.user_id
            )

            moderator = interaction.guild.get_member(
                action.moderator_id
            )

            target_text = (
                target.mention
                if target
                else f"<@{action.user_id}>"
            )

            moderator_text = (
                moderator.mention
                if moderator
                else f"<@{action.moderator_id}>"
            )

            lines.append(
                f"**#{action.id}** `{action.action}`\n"
                f"Usuario: {target_text}\n"
                f"Moderador: {moderator_text}\n"
                f"Razón: {action.reason}\n"
                f"`{action.created_at}`"
            )

        embed.description = "\n\n".join(
            lines
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    # -----------------------------------------------------------------------
    # Timeout
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="timeout",
        description="Aplica un timeout a un usuario.",
    )
    @app_commands.describe(
        usuario="Usuario que recibirá el timeout.",
        duracion="Duración: 10s, 5m, 2h o 7d.",
        razon="Motivo del timeout.",
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def timeout(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        duracion: str,
        razon: str = "Sin razón especificada",
    ) -> None:
        if interaction.guild is None:
            return

        moderator = interaction.user

        if not isinstance(
            moderator,
            discord.Member,
        ):
            return

        if not self._can_moderate(
            moderator,
            usuario,
        ):
            await interaction.response.send_message(
                "No puedes moderar a ese usuario por la jerarquía de roles.",
                ephemeral=True,
            )
            return

        seconds = self._parse_duration(
            duracion
        )

        if seconds is None:
            await interaction.response.send_message(
                "Duración inválida. Usa formatos como "
                "`10s`, `5m`, `2h` o `7d`.",
                ephemeral=True,
            )
            return

        try:
            await usuario.timeout(
                timedelta(
                    seconds=seconds
                ),
                reason=razon,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "No tengo permisos suficientes para aplicar el timeout.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "Discord rechazó el timeout.",
                ephemeral=True,
            )
            return

        self.service.register_action(
            interaction.guild.id,
            usuario.id,
            moderator.id,
            "timeout",
            razon,
            seconds,
        )

        await interaction.response.send_message(
            f"⏱️ {usuario.mention} recibió un timeout de "
            f"**{self._format_duration(seconds)}**.",
            ephemeral=True,
        )

        embed = discord.Embed(
            title="Timeout",
            color=discord.Color.orange(),
        )

        embed.add_field(
            name="Usuario",
            value=usuario.mention,
            inline=True,
        )

        embed.add_field(
            name="Moderador",
            value=moderator.mention,
            inline=True,
        )

        embed.add_field(
            name="Duración",
            value=self._format_duration(
                seconds
            ),
            inline=True,
        )

        embed.add_field(
            name="Razón",
            value=razon,
            inline=False,
        )

        await self._send_log(
            interaction.guild,
            embed,
        )

    # -----------------------------------------------------------------------
    # Mute / Unmute
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="mute",
        description="Silencia temporalmente a un usuario.",
    )
    @app_commands.describe(
        usuario="Usuario que será silenciado.",
        duracion="Duración: 10s, 5m, 2h o 7d.",
        razon="Motivo.",
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def mute(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        duracion: str,
        razon: str = "Sin razón especificada",
    ) -> None:
        await self.timeout(
            interaction,
            usuario,
            duracion,
            razon,
        )

    @app_commands.command(
        name="unmute",
        description="Quita el timeout de un usuario.",
    )
    @app_commands.describe(
        usuario="Usuario al que se quitará el timeout.",
        razon="Motivo.",
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def unmute(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        razon: str = "Sin razón especificada",
    ) -> None:
        if interaction.guild is None:
            return

        moderator = interaction.user

        if not isinstance(
            moderator,
            discord.Member,
        ):
            return

        if not self._can_moderate(
            moderator,
            usuario,
        ):
            await interaction.response.send_message(
                "No puedes moderar a ese usuario.",
                ephemeral=True,
            )
            return

        try:
            await usuario.timeout(
                None,
                reason=razon,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "No tengo permisos suficientes.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "Discord rechazó la operación.",
                ephemeral=True,
            )
            return

        self.service.register_action(
            interaction.guild.id,
            usuario.id,
            moderator.id,
            "unmute",
            razon,
        )

        await interaction.response.send_message(
            f"🔊 Se quitó el timeout a {usuario.mention}.",
            ephemeral=True,
        )

        embed = discord.Embed(
            title="Timeout eliminado",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="Usuario",
            value=usuario.mention,
            inline=True,
        )

        embed.add_field(
            name="Moderador",
            value=moderator.mention,
            inline=True,
        )

        embed.add_field(
            name="Razón",
            value=razon,
            inline=False,
        )

        await self._send_log(
            interaction.guild,
            embed,
        )

    # -----------------------------------------------------------------------
    # Kick
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="kick",
        description="Expulsa a un usuario.",
    )
    @app_commands.describe(
        usuario="Usuario que será expulsado.",
        razon="Motivo de la expulsión.",
    )
    @app_commands.checks.has_permissions(
        kick_members=True
    )
    async def kick(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        razon: str = "Sin razón especificada",
    ) -> None:
        if interaction.guild is None:
            return

        moderator = interaction.user

        if not isinstance(
            moderator,
            discord.Member,
        ):
            return

        if not self._can_moderate(
            moderator,
            usuario,
        ):
            await interaction.response.send_message(
                "No puedes expulsar a ese usuario por la jerarquía de roles.",
                ephemeral=True,
            )
            return

        try:
            await usuario.kick(
                reason=razon
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "No tengo permisos suficientes para expulsar a ese usuario.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "Discord rechazó la expulsión.",
                ephemeral=True,
            )
            return

        self.service.register_action(
            interaction.guild.id,
            usuario.id,
            moderator.id,
            "kick",
            razon,
        )

        await interaction.response.send_message(
            f"👢 {usuario} fue expulsado.",
            ephemeral=True,
        )

        embed = discord.Embed(
            title="Usuario expulsado",
            color=discord.Color.orange(),
        )

        embed.add_field(
            name="Usuario",
            value=f"{usuario} (`{usuario.id}`)",
            inline=False,
        )

        embed.add_field(
            name="Moderador",
            value=moderator.mention,
            inline=True,
        )

        embed.add_field(
            name="Razón",
            value=razon,
            inline=False,
        )

        await self._send_log(
            interaction.guild,
            embed,
        )

    # -----------------------------------------------------------------------
    # Ban
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="ban",
        description="Banea a un usuario.",
    )
    @app_commands.describe(
        usuario="Usuario que será baneado.",
        razon="Motivo del baneo.",
    )
    @app_commands.checks.has_permissions(
        ban_members=True
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        razon: str = "Sin razón especificada",
    ) -> None:
        if interaction.guild is None:
            return

        moderator = interaction.user

        if not isinstance(
            moderator,
            discord.Member,
        ):
            return

        if not self._can_moderate(
            moderator,
            usuario,
        ):
            await interaction.response.send_message(
                "No puedes banear a ese usuario por la jerarquía de roles.",
                ephemeral=True,
            )
            return

        try:
            await usuario.ban(
                reason=razon,
                delete_message_seconds=0,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "No tengo permisos suficientes para banear a ese usuario.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "Discord rechazó el baneo.",
                ephemeral=True,
            )
            return

        self.service.register_action(
            interaction.guild.id,
            usuario.id,
            moderator.id,
            "ban",
            razon,
        )

        await interaction.response.send_message(
            f"🔨 {usuario} fue baneado.",
            ephemeral=True,
        )

        embed = discord.Embed(
            title="Usuario baneado",
            color=discord.Color.red(),
        )

        embed.add_field(
            name="Usuario",
            value=f"{usuario} (`{usuario.id}`)",
            inline=False,
        )

        embed.add_field(
            name="Moderador",
            value=moderator.mention,
            inline=True,
        )

        embed.add_field(
            name="Razón",
            value=razon,
            inline=False,
        )

        await self._send_log(
            interaction.guild,
            embed,
        )

    # -----------------------------------------------------------------------
    # Unban
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="unban",
        description="Quita el baneo de un usuario.",
    )
    @app_commands.describe(
        usuario_id="ID del usuario baneado.",
        razon="Motivo.",
    )
    @app_commands.checks.has_permissions(
        ban_members=True
    )
    async def unban(
        self,
        interaction: discord.Interaction,
        usuario_id: str,
        razon: str = "Sin razón especificada",
    ) -> None:
        if interaction.guild is None:
            return

        try:
            user_id = int(
                usuario_id
            )
        except ValueError:
            await interaction.response.send_message(
                "El ID del usuario no es válido.",
                ephemeral=True,
            )
            return

        if self.bot is None:
            await interaction.response.send_message(
                "El bot todavía no está disponible.",
                ephemeral=True,
            )
            return

        try:
            user = await self.bot.fetch_user(
                user_id
            )

            await interaction.guild.unban(
                user,
                reason=razon,
            )
        except discord.NotFound:
            await interaction.response.send_message(
                "Ese usuario no está baneado o no existe.",
                ephemeral=True,
            )
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                "No tengo permisos suficientes para quitar el baneo.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "Discord rechazó la operación.",
                ephemeral=True,
            )
            return

        self.service.register_action(
            interaction.guild.id,
            user_id,
            interaction.user.id,
            "unban",
            razon,
        )

        await interaction.response.send_message(
            f"🔓 Se quitó el baneo de <@{user_id}>.",
            ephemeral=True,
        )

        embed = discord.Embed(
            title="Baneo eliminado",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="Usuario",
            value=f"<@{user_id}> (`{user_id}`)",
            inline=False,
        )

        embed.add_field(
            name="Moderador",
            value=interaction.user.mention,
            inline=True,
        )

        embed.add_field(
            name="Razón",
            value=razon,
            inline=False,
        )

        await self._send_log(
            interaction.guild,
            embed,
        )

    # -----------------------------------------------------------------------
    # AutoMod configuration command
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="automod",
        description="Configura una regla de AutoMod.",
    )
    @app_commands.describe(
        regla="Regla de AutoMod.",
        accion="Acción que se ejecutará.",
        habilitado="Activa o desactiva la regla.",
        timeout="Timeout en segundos cuando la acción sea timeout.",
    )
    @app_commands.choices(
        regla=[
            app_commands.Choice(
                name=name,
                value=value,
            )
            for value, name
            in AUTOMOD_RULE_NAMES.items()
        ],
        accion=[
            app_commands.Choice(
                name=name,
                value=value,
            )
            for value, name
            in AUTOMOD_ACTIONS.items()
        ],
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def automod(
        self,
        interaction: discord.Interaction,
        regla: app_commands.Choice[str],
        accion: app_commands.Choice[str],
        habilitado: bool = True,
        timeout: int = 600,
    ) -> None:
        if interaction.guild is None:
            return

        self.repository.ensure_default_automod_rules(
            interaction.guild.id
        )

        timeout = max(
            1,
            min(
                timeout,
                28 * 86400,
            ),
        )

        configured = (
            self.repository.configure_automod_rule(
                interaction.guild.id,
                regla.value,
                enabled=habilitado,
                action=accion.value,
                timeout_seconds=timeout,
            )
        )

        status = (
            "🟢 Activada"
            if configured.enabled
            else "🔴 Desactivada"
        )

        await interaction.response.send_message(
            f"**{AUTOMOD_RULE_NAMES.get(regla.value, regla.value)}**\n"
            f"Estado: {status}\n"
            f"Acción: "
            f"{AUTOMOD_ACTIONS.get(accion.value, accion.value)}\n"
            f"Umbral: `{configured.threshold}`\n"
            f"Ventana: `{configured.window_seconds}s`\n"
            f"Timeout: "
            f"{self._format_duration(configured.timeout_seconds)}",
            ephemeral=True,
        )


class ModeracionCog(commands.Cog):
    """Moderation cog."""

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

        self.repository = ModerationRepository()

        self.service = ModerationService(
            self.repository
        )

        self.moderacion_group = ModeracionGroup(
            self.repository,
            self.service,
        )

        self.moderacion_group.bot = bot

    async def cog_load(
        self,
    ) -> None:
        existing = self.bot.tree.get_command(
            "moderacion",
            type=discord.AppCommandType.chat_input,
        )

        if existing is not None:
            LOGGER.warning(
                "The /moderacion command already exists. "
                "Skipping duplicate registration."
            )
            return

        self.bot.tree.add_command(
            self.moderacion_group
        )

        LOGGER.info(
            "Moderation command group registered."
        )

    async def cog_unload(
        self,
    ) -> None:
        existing = self.bot.tree.get_command(
            "moderacion",
            type=discord.AppCommandType.chat_input,
        )

        if existing is self.moderacion_group:
            self.bot.tree.remove_command(
                "moderacion",
                type=discord.AppCommandType.chat_input,
            )

        LOGGER.info(
            "Moderation command group unloaded."
        )

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ) -> None:
        await self.moderacion_group.process_message(
            message
        )


async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(
        ModeracionCog(bot)
    )