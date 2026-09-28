"""Interactive moderation panel for Odinus."""

from __future__ import annotations

import discord

from odinus.services.moderacion import (
    ACTION_NAMES,
    DEFAULT_AUTOMOD_RULES,
    AutomodRule,
    ModerationRepository,
)


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


ACTION_NAMES = {
    "delete": "Eliminar mensaje",
    "warn": "Advertencia",
    "timeout": "Timeout",
}


IMMEDIATE_RULES = {
    "discord_invites",
    "suspicious_links",
    "blocked_words",
    "repeated_chars",
    "repeated_questions",
    "repeated_exclamations",
    "emoji_spam",
}


def _is_admin(
    interaction: discord.Interaction,
) -> bool:
    if interaction.guild is None:
        return False

    member = interaction.user

    return (
        isinstance(member, discord.Member)
        and member.guild_permissions.administrator
    )


def _rule_name(rule: str) -> str:
    return AUTOMOD_RULE_NAMES.get(
        rule,
        rule,
    )


def _action_name(action: str) -> str:
    return ACTION_NAMES.get(
        action,
        action,
    )


def _window_text(
    rule: AutomodRule,
) -> str:
    if rule.window_seconds <= 0:
        return "No aplica"

    return f"{rule.window_seconds} s"


def _threshold_text(
    rule: AutomodRule,
) -> str:
    return str(rule.threshold)


def build_main_embed(
    repository: ModerationRepository,
    guild: discord.Guild,
) -> discord.Embed:
    repository.ensure_default_automod_rules(
        guild.id
    )

    settings = repository.get_settings(
        guild.id
    )

    ignored_channels = repository.get_ignored_channels(
        guild.id
    )

    ignored_roles = repository.get_ignored_roles(
        guild.id
    )

    blocked_words = repository.get_blocked_words(
        guild.id
    )

    rules = repository.get_automod_rules(
        guild.id
    )

    embed = discord.Embed(
        title="🛡️ Panel de Moderación",
        description=(
            "Configura la moderación de **Odinus** "
            "desde este panel.\n\n"
            "Los cambios se guardan automáticamente "
            "en la base de datos."
        ),
        color=(
            discord.Color.green()
            if settings.enabled
            else discord.Color.red()
        ),
    )

    embed.add_field(
        name="Estado",
        value=(
            "🟢 **Activa**"
            if settings.enabled
            else "🔴 **Inactiva**"
        ),
        inline=True,
    )

    if settings.log_channel_id:
        log_channel = guild.get_channel(
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
        value=str(len(ignored_channels)),
        inline=True,
    )

    embed.add_field(
        name="Roles ignorados",
        value=str(len(ignored_roles)),
        inline=True,
    )

    embed.add_field(
        name="Palabras bloqueadas",
        value=str(len(blocked_words)),
        inline=True,
    )

    enabled_count = sum(
        1
        for rule in rules
        if rule.enabled
    )

    embed.add_field(
        name="Reglas AutoMod",
        value=f"{enabled_count}/{len(rules)} activas",
        inline=True,
    )

    lines = []

    for rule in rules:
        status = "🟢" if rule.enabled else "🔴"

        if rule.window_seconds > 0:
            limits = (
                f"{rule.threshold} / "
                f"{rule.window_seconds}s"
            )
        else:
            limits = f"{rule.threshold}"

        lines.append(
            f"{status} **{_rule_name(rule.rule)}** — "
            f"{_action_name(rule.action)} — `{limits}`"
        )

    embed.add_field(
        name="Configuración AutoMod",
        value=(
            "\n".join(lines)
            if lines
            else "No hay reglas configuradas."
        ),
        inline=False,
    )

    embed.set_footer(
        text="Odinus • Moderación"
    )

    return embed


def build_ignored_channels_embed(
    repository: ModerationRepository,
    guild: discord.Guild,
) -> discord.Embed:
    ignored = repository.get_ignored_channels(
        guild.id
    )

    embed = discord.Embed(
        title="🚫 Canales ignorados",
        description=(
            "Los mensajes enviados en estos canales "
            "no serán procesados por AutoMod."
        ),
        color=discord.Color.orange(),
    )

    if not ignored:
        embed.add_field(
            name="Canales",
            value="No hay canales ignorados.",
            inline=False,
        )
    else:
        lines = []

        for channel_id in sorted(ignored):
            channel = guild.get_channel(
                channel_id
            )

            lines.append(
                channel.mention
                if channel
                else f"<#{channel_id}>"
            )

        embed.add_field(
            name="Canales actuales",
            value="\n".join(lines[:25]),
            inline=False,
        )

    return embed


def build_ignored_roles_embed(
    repository: ModerationRepository,
    guild: discord.Guild,
) -> discord.Embed:
    ignored = repository.get_ignored_roles(
        guild.id
    )

    embed = discord.Embed(
        title="🚫 Roles ignorados",
        description=(
            "Los usuarios que tengan alguno de estos roles "
            "no serán procesados por AutoMod."
        ),
        color=discord.Color.orange(),
    )

    if not ignored:
        embed.add_field(
            name="Roles",
            value="No hay roles ignorados.",
            inline=False,
        )
    else:
        lines = []

        for role_id in sorted(ignored):
            role = guild.get_role(
                role_id
            )

            lines.append(
                role.mention
                if role
                else f"<@&{role_id}>"
            )

        embed.add_field(
            name="Roles actuales",
            value="\n".join(lines[:25]),
            inline=False,
        )

    return embed


def build_blocked_words_embed(
    repository: ModerationRepository,
    guild: discord.Guild,
) -> discord.Embed:
    words = sorted(
        repository.get_blocked_words(
            guild.id
        )
    )

    embed = discord.Embed(
        title="🚫 Palabras bloqueadas",
        description=(
            "Las palabras configuradas aquí activarán "
            "la regla **Palabras bloqueadas**."
        ),
        color=discord.Color.orange(),
    )

    if not words:
        embed.add_field(
            name="Palabras",
            value="No hay palabras bloqueadas.",
            inline=False,
        )
    else:
        displayed = words[:50]

        embed.add_field(
            name="Palabras actuales",
            value="\n".join(
                f"• `{word}`"
                for word in displayed
            ),
            inline=False,
        )

        if len(words) > 50:
            embed.set_footer(
                text=(
                    f"Mostrando 50 de {len(words)} palabras."
                )
            )

    return embed


def build_automod_embed(
    repository: ModerationRepository,
    guild: discord.Guild,
) -> discord.Embed:
    repository.ensure_default_automod_rules(
        guild.id
    )

    rules = repository.get_automod_rules(
        guild.id
    )

    embed = discord.Embed(
        title="🤖 AutoMod",
        description=(
            "Selecciona una regla para configurarla."
        ),
        color=discord.Color.blurple(),
    )

    lines = []

    for rule in rules:
        status = "🟢" if rule.enabled else "🔴"

        if rule.window_seconds > 0:
            limits = (
                f"{rule.threshold} en "
                f"{rule.window_seconds}s"
            )
        else:
            limits = str(rule.threshold)

        lines.append(
            f"{status} **{_rule_name(rule.rule)}**\n"
            f"Acción: {_action_name(rule.action)}\n"
            f"Límite: `{limits}`\n"
            f"Timeout: `{rule.timeout_seconds}s`"
        )

    embed.add_field(
        name="Reglas",
        value=(
            "\n\n".join(lines)
            if lines
            else "No hay reglas configuradas."
        ),
        inline=False,
    )

    return embed


def build_rule_embed(
    rule: AutomodRule,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"⚙️ {_rule_name(rule.rule)}",
        color=(
            discord.Color.green()
            if rule.enabled
            else discord.Color.red()
        ),
    )

    embed.add_field(
        name="Estado",
        value=(
            "🟢 Activada"
            if rule.enabled
            else "🔴 Desactivada"
        ),
        inline=True,
    )

    embed.add_field(
        name="Acción",
        value=_action_name(rule.action),
        inline=True,
    )

    embed.add_field(
        name="Timeout",
        value=f"{rule.timeout_seconds} segundos",
        inline=True,
    )

    embed.add_field(
        name="Umbral",
        value=_threshold_text(rule),
        inline=True,
    )

    embed.add_field(
        name="Ventana",
        value=_window_text(rule),
        inline=True,
    )

    if rule.rule in IMMEDIATE_RULES:
        if rule.rule in {
            "discord_invites",
            "suspicious_links",
            "blocked_words",
        }:
            explanation = "Detección inmediata."
        else:
            explanation = "Se evalúa dentro del mensaje."

        embed.add_field(
            name="Tipo",
            value=explanation,
            inline=True,
        )

    return embed


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------


class ModeracionPanelView(discord.ui.View):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
    ) -> None:
        super().__init__(
            timeout=900
        )

        self.repository = repository
        self.guild_id = guild_id

        settings = repository.get_settings(
            guild_id
        )

        toggle = discord.ui.Button(
            label=(
                "Desactivar moderación"
                if settings.enabled
                else "Activar moderación"
            ),
            emoji="🔴" if settings.enabled else "🟢",
            style=(
                discord.ButtonStyle.danger
                if settings.enabled
                else discord.ButtonStyle.success
            ),
            row=0,
        )

        toggle.callback = self.toggle_callback
        self.add_item(toggle)

        logs = discord.ui.Button(
            label="Canal de registros",
            emoji="📋",
            style=discord.ButtonStyle.primary,
            row=0,
        )
        logs.callback = self.logs_callback
        self.add_item(logs)

        automod = discord.ui.Button(
            label="AutoMod",
            emoji="🤖",
            style=discord.ButtonStyle.primary,
            row=0,
        )
        automod.callback = self.automod_callback
        self.add_item(automod)

        channels = discord.ui.Button(
            label="Canales ignorados",
            emoji="🚫",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        channels.callback = self.channels_callback
        self.add_item(channels)

        roles = discord.ui.Button(
            label="Roles ignorados",
            emoji="👤",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        roles.callback = self.roles_callback
        self.add_item(roles)

        words = discord.ui.Button(
            label="Palabras bloqueadas",
            emoji="🔤",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        words.callback = self.words_callback
        self.add_item(words)

        refresh = discord.ui.Button(
            label="Actualizar",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        refresh.callback = self.refresh_callback
        self.add_item(refresh)

        close = discord.ui.Button(
            label="Cerrar",
            emoji="✖️",
            style=discord.ButtonStyle.danger,
            row=2,
        )
        close.callback = self.close_callback
        self.add_item(close)

    async def toggle_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos para utilizar este panel.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        current = self.repository.get_settings(
            guild.id
        )

        self.repository.set_enabled(
            guild.id,
            not current.enabled,
        )

        await interaction.response.edit_message(
            embed=build_main_embed(
                self.repository,
                guild,
            ),
            view=ModeracionPanelView(
                self.repository,
                guild.id,
            ),
        )

    async def logs_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="📋 Canal de registros",
                description=(
                    "Selecciona el canal privado donde Odinus "
                    "enviará los registros de moderación."
                ),
                color=discord.Color.blurple(),
            ),
            view=ModeracionLogsView(
                self.repository,
                guild.id,
            ),
        )

    async def automod_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        self.repository.ensure_default_automod_rules(
            guild.id
        )

        await interaction.response.edit_message(
            embed=build_automod_embed(
                self.repository,
                guild,
            ),
            view=AutoModView(
                self.repository,
                guild.id,
            ),
        )

    async def channels_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_ignored_channels_embed(
                self.repository,
                guild,
            ),
            view=IgnoredChannelsView(
                self.repository,
                guild.id,
            ),
        )

    async def roles_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_ignored_roles_embed(
                self.repository,
                guild,
            ),
            view=IgnoredRolesView(
                self.repository,
                guild.id,
            ),
        )

    async def words_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_blocked_words_embed(
                self.repository,
                guild,
            ),
            view=BlockedWordsView(
                self.repository,
                guild.id,
            ),
        )

    async def refresh_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_main_embed(
                self.repository,
                guild,
            ),
            view=ModeracionPanelView(
                self.repository,
                guild.id,
            ),
        )

    async def close_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            content="🛡️ Panel de moderación cerrado.",
            embed=None,
            view=None,
        )


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


class ModeracionLogsView(discord.ui.View):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
    ) -> None:
        super().__init__(
            timeout=900
        )

        self.repository = repository
        self.guild_id = guild_id

        select = discord.ui.ChannelSelect(
            placeholder="Selecciona el canal de registros...",
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news,
            ],
            min_values=1,
            max_values=1,
            row=0,
        )

        select.callback = self.channel_selected
        self.add_item(select)

        clear = discord.ui.Button(
            label="Quitar canal",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            row=1,
        )
        clear.callback = self.clear_channel
        self.add_item(clear)

        back = discord.ui.Button(
            label="Volver",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        back.callback = self.back
        self.add_item(back)

    async def channel_selected(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        select = self.children[0]

        if not isinstance(
            select,
            discord.ui.ChannelSelect,
        ):
            await interaction.response.send_message(
                "No se pudo obtener el selector de canales.",
                ephemeral=True,
            )
            return

        if not select.values:
            await interaction.response.send_message(
                "No se seleccionó ningún canal.",
                ephemeral=True,
            )
            return

        selected = select.values[0]

        # En discord.py, los canales de texto y los canales de
        # anuncios/noticias compatibles con ChannelSelect se manejan
        # mediante TextChannel. No existe discord.NewsChannel.
        if not isinstance(
            selected,
            discord.TextChannel,
        ):
            await interaction.response.send_message(
                "Selecciona un canal de texto válido.",
                ephemeral=True,
            )
            return

        self.repository.set_log_channel(
            self.guild_id,
            selected.id,
        )

        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "Esta acción solo puede utilizarse dentro de un servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            content=None,
            embed=build_main_embed(
                self.repository,
                guild,
            ),
            view=ModeracionPanelView(
                self.repository,
                guild.id,
            ),
        )

    async def clear_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        self.repository.set_log_channel(
            self.guild_id,
            None,
        )

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            content=None,
            embed=build_main_embed(
                self.repository,
                guild,
            ),
            view=ModeracionPanelView(
                self.repository,
                guild.id,
            ),
        )

    async def back(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            content=None,
            embed=build_main_embed(
                self.repository,
                guild,
            ),
            view=ModeracionPanelView(
                self.repository,
                guild.id,
            ),
        )


# ---------------------------------------------------------------------------
# Ignored channels
# ---------------------------------------------------------------------------


class IgnoredChannelsView(discord.ui.View):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
    ) -> None:
        super().__init__(
            timeout=900
        )

        self.repository = repository
        self.guild_id = guild_id

        add = discord.ui.ChannelSelect(
            placeholder="Añadir canal ignorado...",
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news,
                discord.ChannelType.forum,
            ],
            min_values=1,
            max_values=1,
            row=0,
        )
        add.callback = self.add_channel
        self.add_item(add)

        remove = discord.ui.ChannelSelect(
            placeholder="Quitar canal ignorado...",
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news,
                discord.ChannelType.forum,
            ],
            min_values=1,
            max_values=1,
            row=1,
        )
        remove.callback = self.remove_channel
        self.add_item(remove)

        back = discord.ui.Button(
            label="Volver",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        back.callback = self.back
        self.add_item(back)

    async def add_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        select = self.children[0]

        if not isinstance(
            select,
            discord.ui.ChannelSelect,
        ):
            return

        if not select.values:
            await interaction.response.send_message(
                "No se seleccionó ningún canal.",
                ephemeral=True,
            )
            return

        channel = select.values[0]

        self.repository.add_ignored_channel(
            self.guild_id,
            channel.id,
        )

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_ignored_channels_embed(
                self.repository,
                guild,
            ),
            view=IgnoredChannelsView(
                self.repository,
                guild.id,
            ),
        )

    async def remove_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        select = self.children[1]

        if not isinstance(
            select,
            discord.ui.ChannelSelect,
        ):
            return

        if not select.values:
            await interaction.response.send_message(
                "No se seleccionó ningún canal.",
                ephemeral=True,
            )
            return

        channel = select.values[0]

        self.repository.remove_ignored_channel(
            self.guild_id,
            channel.id,
        )

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_ignored_channels_embed(
                self.repository,
                guild,
            ),
            view=IgnoredChannelsView(
                self.repository,
                guild.id,
            ),
        )

    async def back(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_main_embed(
                self.repository,
                guild,
            ),
            view=ModeracionPanelView(
                self.repository,
                guild.id,
            ),
        )


# ---------------------------------------------------------------------------
# Ignored roles
# ---------------------------------------------------------------------------


class IgnoredRolesView(discord.ui.View):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
    ) -> None:
        super().__init__(
            timeout=900
        )

        self.repository = repository
        self.guild_id = guild_id

        add = discord.ui.RoleSelect(
            placeholder="Añadir rol ignorado...",
            min_values=1,
            max_values=1,
            row=0,
        )
        add.callback = self.add_role
        self.add_item(add)

        remove = discord.ui.RoleSelect(
            placeholder="Quitar rol ignorado...",
            min_values=1,
            max_values=1,
            row=1,
        )
        remove.callback = self.remove_role
        self.add_item(remove)

        back = discord.ui.Button(
            label="Volver",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        back.callback = self.back
        self.add_item(back)

    async def add_role(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        select = self.children[0]

        if not isinstance(
            select,
            discord.ui.RoleSelect,
        ):
            return

        if not select.values:
            await interaction.response.send_message(
                "No se seleccionó ningún rol.",
                ephemeral=True,
            )
            return

        role = select.values[0]

        if role.is_default():
            await interaction.response.send_message(
                "No se puede ignorar el rol @everyone.",
                ephemeral=True,
            )
            return

        self.repository.add_ignored_role(
            self.guild_id,
            role.id,
        )

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_ignored_roles_embed(
                self.repository,
                guild,
            ),
            view=IgnoredRolesView(
                self.repository,
                guild.id,
            ),
        )

    async def remove_role(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        select = self.children[1]

        if not isinstance(
            select,
            discord.ui.RoleSelect,
        ):
            return

        if not select.values:
            await interaction.response.send_message(
                "No se seleccionó ningún rol.",
                ephemeral=True,
            )
            return

        role = select.values[0]

        self.repository.remove_ignored_role(
            self.guild_id,
            role.id,
        )

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_ignored_roles_embed(
                self.repository,
                guild,
            ),
            view=IgnoredRolesView(
                self.repository,
                guild.id,
            ),
        )

    async def back(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_main_embed(
                self.repository,
                guild,
            ),
            view=ModeracionPanelView(
                self.repository,
                guild.id,
            ),
        )


# ---------------------------------------------------------------------------
# Blocked words
# ---------------------------------------------------------------------------


class AddBlockedWordModal(discord.ui.Modal):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
    ) -> None:
        super().__init__(
            title="Añadir palabra bloqueada"
        )

        self.repository = repository
        self.guild_id = guild_id

        self.word = discord.ui.TextInput(
            label="Palabra o frase",
            placeholder="Ejemplo: palabra prohibida",
            required=True,
            min_length=1,
            max_length=100,
        )

        self.add_item(
            self.word
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        word = str(
            self.word.value
        ).strip()

        if not word:
            await interaction.response.send_message(
                "La palabra no puede estar vacía.",
                ephemeral=True,
            )
            return

        self.repository.add_blocked_word(
            self.guild_id,
            word,
        )

        await interaction.response.send_message(
            f"✅ Se añadió `{word.lower()}` a las palabras bloqueadas.",
            ephemeral=True,
        )


class RemoveBlockedWordModal(discord.ui.Modal):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
    ) -> None:
        super().__init__(
            title="Eliminar palabra bloqueada"
        )

        self.repository = repository
        self.guild_id = guild_id

        self.word = discord.ui.TextInput(
            label="Palabra o frase",
            placeholder="Escribe exactamente la palabra a eliminar",
            required=True,
            min_length=1,
            max_length=100,
        )

        self.add_item(
            self.word
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        word = str(
            self.word.value
        ).strip()

        if not word:
            await interaction.response.send_message(
                "La palabra no puede estar vacía.",
                ephemeral=True,
            )
            return

        self.repository.remove_blocked_word(
            self.guild_id,
            word,
        )

        await interaction.response.send_message(
            f"✅ Se eliminó `{word.lower()}` de las palabras bloqueadas.",
            ephemeral=True,
        )


class BlockedWordsView(discord.ui.View):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
    ) -> None:
        super().__init__(
            timeout=900
        )

        self.repository = repository
        self.guild_id = guild_id

        add = discord.ui.Button(
            label="Añadir",
            emoji="➕",
            style=discord.ButtonStyle.success,
            row=0,
        )
        add.callback = self.add_word
        self.add_item(add)

        remove = discord.ui.Button(
            label="Eliminar",
            emoji="➖",
            style=discord.ButtonStyle.danger,
            row=0,
        )
        remove.callback = self.remove_word
        self.add_item(remove)

        back = discord.ui.Button(
            label="Volver",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        back.callback = self.back
        self.add_item(back)

    async def add_word(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            AddBlockedWordModal(
                self.repository,
                self.guild_id,
            )
        )

    async def remove_word(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            RemoveBlockedWordModal(
                self.repository,
                self.guild_id,
            )
        )

    async def back(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_main_embed(
                self.repository,
                guild,
            ),
            view=ModeracionPanelView(
                self.repository,
                guild.id,
            ),
        )


# ---------------------------------------------------------------------------
# AutoMod
# ---------------------------------------------------------------------------


class AutoModRuleSelect(
    discord.ui.Select
):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
    ) -> None:
        options = [
            discord.SelectOption(
                label=name,
                value=value,
            )
            for value, name in AUTOMOD_RULE_NAMES.items()
        ]

        super().__init__(
            placeholder="Selecciona una regla...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

        self.repository = repository
        self.guild_id = guild_id

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        rule_name = self.values[0]

        rule = self.repository.get_automod_rule(
            self.guild_id,
            rule_name,
        )

        if rule is None:
            await interaction.response.send_message(
                "No se pudo cargar la regla.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=build_rule_embed(rule),
            view=AutoModRuleView(
                self.repository,
                self.guild_id,
                rule_name,
            ),
        )


class AutoModView(discord.ui.View):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
    ) -> None:
        super().__init__(
            timeout=900
        )

        self.repository = repository
        self.guild_id = guild_id

        self.add_item(
            AutoModRuleSelect(
                repository,
                guild_id,
            )
        )

        back = discord.ui.Button(
            label="Volver",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        back.callback = self.back
        self.add_item(back)

    async def back(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_main_embed(
                self.repository,
                guild,
            ),
            view=ModeracionPanelView(
                self.repository,
                guild.id,
            ),
        )


# ---------------------------------------------------------------------------
# AutoMod action select
# ---------------------------------------------------------------------------


class AutoModActionSelect(
    discord.ui.Select
):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
        rule_name: str,
        current_action: str,
    ) -> None:
        options = [
            discord.SelectOption(
                label="Eliminar mensaje",
                value="delete",
                default=current_action == "delete",
            ),
            discord.SelectOption(
                label="Advertencia",
                value="warn",
                default=current_action == "warn",
            ),
            discord.SelectOption(
                label="Timeout",
                value="timeout",
                default=current_action == "timeout",
            ),
        ]

        super().__init__(
            placeholder="Selecciona la acción...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

        self.repository = repository
        self.guild_id = guild_id
        self.rule_name = rule_name

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        self.repository.configure_automod_rule(
            self.guild_id,
            self.rule_name,
            action=self.values[0],
        )

        rule = self.repository.get_automod_rule(
            self.guild_id,
            self.rule_name,
        )

        if rule is None:
            await interaction.response.send_message(
                "No se pudo actualizar la regla.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=build_rule_embed(rule),
            view=AutoModRuleView(
                self.repository,
                self.guild_id,
                self.rule_name,
            ),
        )


# ---------------------------------------------------------------------------
# AutoMod configuration modal
# ---------------------------------------------------------------------------


class AutoModConfigModal(discord.ui.Modal):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
        rule: AutomodRule,
    ) -> None:
        super().__init__(
            title=f"Configurar {_rule_name(rule.rule)}"
        )

        self.repository = repository
        self.guild_id = guild_id
        self.rule_name = rule.rule

        self.threshold = discord.ui.TextInput(
            label="Umbral",
            placeholder="Ejemplo: 5",
            default=str(rule.threshold),
            required=True,
            min_length=1,
            max_length=4,
        )

        self.window = discord.ui.TextInput(
            label="Ventana en segundos",
            placeholder="Ejemplo: 60",
            default=str(rule.window_seconds),
            required=True,
            min_length=1,
            max_length=4,
        )

        self.timeout_input = discord.ui.TextInput(
            label="Timeout en segundos",
            placeholder="Ejemplo: 600",
            default=str(rule.timeout_seconds),
            required=True,
            min_length=1,
            max_length=7,
        )

        self.add_item(
            self.threshold
        )

        self.add_item(
            self.window
        )

        self.add_item(
            self.timeout_input
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        try:
            threshold = int(
                str(self.threshold.value).strip()
            )

            window = int(
                str(self.window.value).strip()
            )

            timeout = int(
                str(self.timeout_input.value).strip()
            )

        except ValueError:
            await interaction.response.send_message(
                "Todos los valores deben ser números enteros.",
                ephemeral=True,
            )
            return

        if threshold < 1 or threshold > 1000:
            await interaction.response.send_message(
                "El umbral debe estar entre 1 y 1000.",
                ephemeral=True,
            )
            return

        if window < 0 or window > 3600:
            await interaction.response.send_message(
                "La ventana debe estar entre 0 y 3600 segundos.",
                ephemeral=True,
            )
            return

        if timeout < 1 or timeout > 28 * 86400:
            await interaction.response.send_message(
                "El timeout debe estar entre 1 segundo y 28 días.",
                ephemeral=True,
            )
            return

        rule = self.repository.configure_automod_rule(
            self.guild_id,
            self.rule_name,
            threshold=threshold,
            window_seconds=window,
            timeout_seconds=timeout,
        )

        await interaction.response.send_message(
            embed=build_rule_embed(rule),
            view=AutoModRuleView(
                self.repository,
                self.guild_id,
                self.rule_name,
            ),
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# AutoMod rule view
# ---------------------------------------------------------------------------


class AutoModRuleView(discord.ui.View):
    def __init__(
        self,
        repository: ModerationRepository,
        guild_id: int,
        rule_name: str,
    ) -> None:
        super().__init__(
            timeout=900
        )

        self.repository = repository
        self.guild_id = guild_id
        self.rule_name = rule_name

        rule = repository.get_automod_rule(
            guild_id,
            rule_name,
        )

        if rule is None:
            return

        self.add_item(
            AutoModActionSelect(
                repository,
                guild_id,
                rule_name,
                rule.action,
            )
        )

        toggle = discord.ui.Button(
            label=(
                "Desactivar regla"
                if rule.enabled
                else "Activar regla"
            ),
            emoji="🔴" if rule.enabled else "🟢",
            style=(
                discord.ButtonStyle.danger
                if rule.enabled
                else discord.ButtonStyle.success
            ),
            row=1,
        )

        toggle.callback = self.toggle
        self.add_item(toggle)

        configure = discord.ui.Button(
            label="Configurar valores",
            emoji="⚙️",
            style=discord.ButtonStyle.primary,
            row=1,
        )

        configure.callback = self.configure
        self.add_item(configure)

        reset = discord.ui.Button(
            label="Restaurar valores",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
            row=2,
        )

        reset.callback = self.reset
        self.add_item(reset)

        back = discord.ui.Button(
            label="Volver",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=2,
        )

        back.callback = self.back
        self.add_item(back)

    async def toggle(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        rule = self.repository.get_automod_rule(
            self.guild_id,
            self.rule_name,
        )

        if rule is None:
            await interaction.response.send_message(
                "No se pudo cargar la regla.",
                ephemeral=True,
            )
            return

        updated = self.repository.configure_automod_rule(
            self.guild_id,
            self.rule_name,
            enabled=not rule.enabled,
        )

        await interaction.response.edit_message(
            embed=build_rule_embed(updated),
            view=AutoModRuleView(
                self.repository,
                self.guild_id,
                self.rule_name,
            ),
        )

    async def configure(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        rule = self.repository.get_automod_rule(
            self.guild_id,
            self.rule_name,
        )

        if rule is None:
            await interaction.response.send_message(
                "No se pudo cargar la regla.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            AutoModConfigModal(
                self.repository,
                self.guild_id,
                rule,
            )
        )

    async def reset(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        defaults = DEFAULT_AUTOMOD_RULES.get(
            self.rule_name
        )

        if defaults is None:
            await interaction.response.send_message(
                "No existen valores predeterminados para esta regla.",
                ephemeral=True,
            )
            return

        rule = self.repository.configure_automod_rule(
            self.guild_id,
            self.rule_name,
            enabled=bool(
                defaults["enabled"]
            ),
            action=str(
                defaults["action"]
            ),
            timeout_seconds=int(
                defaults["timeout_seconds"]
            ),
            threshold=int(
                defaults["threshold"]
            ),
            window_seconds=int(
                defaults["window_seconds"]
            ),
        )

        await interaction.response.edit_message(
            embed=build_rule_embed(rule),
            view=AutoModRuleView(
                self.repository,
                self.guild_id,
                self.rule_name,
            ),
        )

    async def back(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message(
                "No tienes permisos.",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.edit_message(
            embed=build_automod_embed(
                self.repository,
                guild,
            ),
            view=AutoModView(
                self.repository,
                guild.id,
            ),
        )