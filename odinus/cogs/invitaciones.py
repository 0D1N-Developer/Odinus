"""Invite Management commands and detailed member-join tracking."""

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
    """Configure and publish detailed server invitation activity."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repository = InvitationRepository()
        self.invite_uses: dict[int, dict[str, int]] = {}
        self.guild_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def cog_load(self) -> None:
        """Initialize persistent settings before the bot receives events."""
        self.repository.initialize()

    @app_commands.command(
        name="configurar_canal",
        description="Configura el canal de seguimiento de invitaciones.",
    )
    @app_commands.describe(canal="Canal donde se registrarán las invitaciones.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def configurar_canal(
        self, interaction: discord.Interaction, canal: discord.TextChannel
    ) -> None:
        """Save the tracking channel from a private administrator channel."""
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

        bot_member = interaction.guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Necesito el permiso **Gestionar servidor** para seguir invitaciones.",
                ephemeral=True,
            )
            return

        self.repository.set_channel(interaction.guild.id, canal.id)
        await self._cache_guild_invites(interaction.guild)
        await interaction.response.send_message(
            f"El seguimiento de invitaciones se enviará a {canal.mention}.",
            ephemeral=True,
        )

    @configurar_canal.error
    async def configurar_canal_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Explain failed administrator checks privately."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "No tienes permiso para configurar el seguimiento de invitaciones.",
                ephemeral=True,
            )
            return
        raise error

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Build a baseline of invitation use counts for every server."""
        await asyncio.gather(
            *(self._cache_guild_invites(guild) for guild in self.bot.guilds)
        )

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        """Add newly created invitations to the in-memory baseline."""
        if invite.guild is None:
            return
        self.invite_uses.setdefault(invite.guild.id, {})[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        """Remove deleted invitations from the in-memory baseline."""
        if invite.guild is None:
            return
        self.invite_uses.get(invite.guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Post detailed information about the invitation used by a new member."""
        channel_id = self.repository.channel_id_for_guild(member.guild.id)
        if channel_id is None:
            return

        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            LOGGER.warning(
                "Invitation tracking channel unavailable for guild_id=%s.",
                member.guild.id,
            )
            return

        used_invite, inviter_total = await self._find_used_invite(member.guild)
        await channel.send(
            embed=self._build_join_embed(member, used_invite, inviter_total)
        )

    async def _cache_guild_invites(self, guild: discord.Guild) -> None:
        """Cache the current use count for every active guild invitation."""
        try:
            invites = await guild.invites()
        except discord.Forbidden:
            LOGGER.warning(
                "Missing Manage Guild permission for invitation tracking in guild_id=%s.",
                guild.id,
            )
            return
        except discord.HTTPException:
            LOGGER.exception("Unable to fetch invitations for guild_id=%s.", guild.id)
            return

        self.invite_uses[guild.id] = {
            invite.code: invite.uses or 0 for invite in invites
        }

    async def _find_used_invite(
        self, guild: discord.Guild
    ) -> tuple[discord.Invite | None, int | None]:
        """Compare invite use counts safely to identify a member's invitation."""
        async with self.guild_locks[guild.id]:
            before_uses = self.invite_uses.get(guild.id, {})
            try:
                invites = await guild.invites()
            except discord.Forbidden:
                LOGGER.warning(
                    "Missing Manage Guild permission while tracking guild_id=%s.",
                    guild.id,
                )
                return None, None
            except discord.HTTPException:
                LOGGER.exception("Unable to compare invitations for guild_id=%s.", guild.id)
                return None, None

            used_invite = next(
                (
                    invite
                    for invite in invites
                    if (invite.uses or 0) > before_uses.get(invite.code, 0)
                ),
                None,
            )
            self.invite_uses[guild.id] = {
                invite.code: invite.uses or 0 for invite in invites
            }
            if used_invite is None or used_invite.inviter is None:
                return used_invite, None

            inviter_total = sum(
                invite.uses or 0
                for invite in invites
                if invite.inviter is not None
                and invite.inviter.id == used_invite.inviter.id
            )
            return used_invite, inviter_total

    @staticmethod
    def _build_join_embed(
        member: discord.Member,
        invite: discord.Invite | None,
        inviter_total: int | None,
    ) -> discord.Embed:
        """Build the detailed invitation tracking event sent to administrators."""
        embed = discord.Embed(
            title="📨 Nuevo miembro",
            description=f"{member.mention} se unió al servidor.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Cuenta creada",
            value=discord.utils.format_dt(member.created_at, style="R"),
            inline=True,
        )

        if invite is None:
            embed.add_field(
                name="Invitación",
                value="No se pudo identificar la invitación utilizada.",
                inline=False,
            )
        else:
            inviter = (
                invite.inviter.mention
                if invite.inviter is not None
                else "Desconocido"
            )
            embed.add_field(name="Invitado por", value=inviter, inline=True)
            embed.add_field(
                name="Invitación",
                value=f"https://discord.gg/{invite.code}",
                inline=True,
            )
            embed.add_field(name="Usos", value=str(invite.uses or 0), inline=True)
            if inviter_total is not None:
                invitation_label = "invitacion" if inviter_total == 1 else "invitaciones"
                embed.add_field(
                    name="Invitaciones en el servidor",
                    value=f"{inviter} ya lleva **{inviter_total} {invitation_label}**.",
                    inline=False,
                )

        embed.set_footer(text="Odinus • Invite Management")
        return embed


async def setup(bot: commands.Bot) -> None:
    """Register the invitation tracking command group with Odinus."""
    await bot.add_cog(InvitacionesCog(bot))
