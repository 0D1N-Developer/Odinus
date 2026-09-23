"""Invite management and detailed member-join tracking."""

from __future__ import annotations

import asyncio
from collections import defaultdict
import logging

import discord
from discord import app_commands
from discord.ext import commands

from odinus.services.invitations import InvitationRepository


LOGGER = logging.getLogger(__name__)


class InvitacionesCog(
    commands.GroupCog,
    group_name="invitaciones",
    group_description="Gestiona el seguimiento de invitaciones.",
):
    """Configure and track server invitation activity."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repository = InvitationRepository()

        self.invite_uses: dict[int, dict[str, int]] = {}

        self.guild_locks: defaultdict[int, asyncio.Lock] = defaultdict(
            asyncio.Lock
        )

    async def cog_load(self) -> None:
        """Initialize persistent invitation storage."""
        self.repository.initialize()

    @app_commands.command(
        name="configurar_canal",
        description="Configura el canal de seguimiento de invitaciones.",
    )
    @app_commands.describe(
        canal="Canal donde se registrarán las invitaciones.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def configurar_canal(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        """Configure the invitation tracking channel."""
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "Este comando solo puede usarse desde un canal "
                "privado del servidor.",
                ephemeral=True,
            )
            return

        if interaction.channel.permissions_for(
            interaction.guild.default_role
        ).view_channel:
            await interaction.response.send_message(
                "Utiliza este comando desde un canal privado "
                "de administración.",
                ephemeral=True,
            )
            return

        bot_member = interaction.guild.me

        if (
            bot_member is None
            or not bot_member.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                "Necesito el permiso **Gestionar servidor** "
                "para seguir invitaciones.",
                ephemeral=True,
            )
            return

        self.repository.set_channel(
            interaction.guild.id,
            canal.id,
        )

        await self._synchronize_guild_invites(
            interaction.guild
        )

        await interaction.response.send_message(
            f"El seguimiento de invitaciones se enviará a "
            f"{canal.mention}.",
            ephemeral=True,
        )

    @configurar_canal.error
    async def configurar_canal_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Explain failed administrator checks privately."""
        if isinstance(
            error,
            app_commands.MissingPermissions,
        ):
            await interaction.response.send_message(
                "No tienes permiso para configurar "
                "el seguimiento de invitaciones.",
                ephemeral=True,
            )
            return

        raise error

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Synchronize invitation history for every server."""
        await asyncio.gather(
            *(
                self._synchronize_guild_invites(guild)
                for guild in self.bot.guilds
            )
        )

    @commands.Cog.listener()
    async def on_invite_create(
        self,
        invite: discord.Invite,
    ) -> None:
        """Register a newly created invitation."""
        if invite.guild is None:
            return

        guild_id = invite.guild.id
        uses = invite.uses or 0
        inviter_id = (
            invite.inviter.id
            if invite.inviter is not None
            else None
        )

        self.repository.record_invite(
            guild_id=guild_id,
            invite_code=invite.code,
            inviter_id=inviter_id,
            uses=uses,
        )

        self.invite_uses.setdefault(
            guild_id,
            {},
        )[invite.code] = uses

    @commands.Cog.listener()
    async def on_invite_delete(
        self,
        invite: discord.Invite,
    ) -> None:
        """
        Keep deleted invitations out of the live cache.

        The persistent invitation record is intentionally preserved
        so historical invitation totals are never lost.
        """
        if invite.guild is None:
            return

        self.invite_uses.get(
            invite.guild.id,
            {},
        ).pop(
            invite.code,
            None,
        )

    @commands.Cog.listener()
    async def on_member_join(
        self,
        member: discord.Member,
    ) -> None:
        """Track and announce a newly joined member."""
        channel_id = self.repository.channel_id_for_guild(
            member.guild.id
        )

        used_invite, inviter_total = await self._find_used_invite(
            member.guild
        )

        if (
            used_invite is not None
            and used_invite.inviter is not None
        ):
            inviter_id = used_invite.inviter.id

            persistent_total = (
                self.repository.increment_user_invites(
                    guild_id=member.guild.id,
                    user_id=inviter_id,
                )
            )

            inviter_total = persistent_total

            # Mark the newly consumed use as processed.
            self.repository.record_invite(
                guild_id=member.guild.id,
                invite_code=used_invite.code,
                inviter_id=inviter_id,
                uses=used_invite.uses or 0,
            )

        if channel_id is None:
            return

        channel = self.bot.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            LOGGER.warning(
                "Invitation tracking channel unavailable "
                "for guild_id=%s.",
                member.guild.id,
            )
            return

        await channel.send(
            embed=self._build_join_embed(
                member,
                used_invite,
                inviter_total,
            )
        )

    async def _synchronize_guild_invites(
        self,
        guild: discord.Guild,
    ) -> None:
        """
        Synchronize active Discord invitation usage with persistent data.

        Existing uses are imported only once. Future increases are
        added as deltas, while deleted invitations remain in history.
        """
        try:
            invites = await guild.invites()

        except discord.Forbidden:
            LOGGER.warning(
                "Missing Manage Guild permission for invitation "
                "tracking in guild_id=%s.",
                guild.id,
            )
            return

        except discord.HTTPException:
            LOGGER.exception(
                "Unable to synchronize invitations "
                "for guild_id=%s.",
                guild.id,
            )
            return

        live_uses: dict[str, int] = {}

        for invite in invites:
            uses = invite.uses or 0

            inviter_id = (
                invite.inviter.id
                if invite.inviter is not None
                else None
            )

            self.repository.sync_invite_usage(
                guild_id=guild.id,
                invite_code=invite.code,
                inviter_id=inviter_id,
                current_uses=uses,
            )

            live_uses[invite.code] = uses

        self.invite_uses[guild.id] = live_uses

    async def _find_used_invite(
        self,
        guild: discord.Guild,
    ) -> tuple[discord.Invite | None, int | None]:
        """Compare invite counts to identify the used invitation."""
        async with self.guild_locks[guild.id]:
            before_uses = self.invite_uses.get(
                guild.id,
                {},
            )

            try:
                invites = await guild.invites()

            except discord.Forbidden:
                LOGGER.warning(
                    "Missing Manage Guild permission while "
                    "tracking guild_id=%s.",
                    guild.id,
                )
                return None, None

            except discord.HTTPException:
                LOGGER.exception(
                    "Unable to compare invitations "
                    "for guild_id=%s.",
                    guild.id,
                )
                return None, None

            used_invite = next(
                (
                    invite
                    for invite in invites
                    if (invite.uses or 0)
                    > before_uses.get(invite.code, 0)
                ),
                None,
            )

            self.invite_uses[guild.id] = {
                invite.code: invite.uses or 0
                for invite in invites
            }

            if (
                used_invite is None
                or used_invite.inviter is None
            ):
                return used_invite, None

            inviter_total = self.repository.user_invites(
                guild_id=guild.id,
                user_id=used_invite.inviter.id,
            )

            return used_invite, inviter_total

    @staticmethod
    def _build_join_embed(
        member: discord.Member,
        invite: discord.Invite | None,
        inviter_total: int | None,
    ) -> discord.Embed:
        """Build the administrator join notification."""
        embed = discord.Embed(
            title="📨 Nuevo miembro",
            description=(
                f"{member.mention} se unió al servidor."
            ),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        embed.add_field(
            name="Cuenta creada",
            value=discord.utils.format_dt(
                member.created_at,
                style="R",
            ),
            inline=True,
        )

        if invite is None:
            embed.add_field(
                name="Invitación",
                value=(
                    "No se pudo identificar la invitación utilizada."
                ),
                inline=False,
            )

        else:
            inviter = (
                invite.inviter.mention
                if invite.inviter is not None
                else "Desconocido"
            )

            embed.add_field(
                name="Invitado por",
                value=inviter,
                inline=True,
            )

            embed.add_field(
                name="Invitación",
                value=f"https://discord.gg/{invite.code}",
                inline=True,
            )

            embed.add_field(
                name="Usos",
                value=str(invite.uses or 0),
                inline=True,
            )

            if inviter_total is not None:
                invitation_label = (
                    "invitación"
                    if inviter_total == 1
                    else "invitaciones"
                )

                embed.add_field(
                    name="Invitaciones en el servidor",
                    value=(
                        f"{inviter} ya lleva **{inviter_total} "
                        f"{invitation_label}**."
                    ),
                    inline=False,
                )

        embed.set_footer(
            text="Odinus • Invite Management"
        )

        return embed


async def setup(bot: commands.Bot) -> None:
    """Register invitation tracking."""
    await bot.add_cog(
        InvitacionesCog(bot)
    )