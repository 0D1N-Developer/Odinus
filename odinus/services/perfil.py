"""Profile aggregation service for Odinus."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import discord

from odinus.cogs.edad import AGE_ROLES, age_role_name
from odinus.cogs.paises import COUNTRIES, role_name
from odinus.services.birthdays import BirthdayRepository
from odinus.services.invitations import InvitationRepository
from odinus.services.niveles import LevelService, UserLevelData
from odinus.services.recompensas import RewardService


@dataclass(slots=True)
class ProfileData:
    """Aggregated profile information for a Discord member."""

    member: discord.Member
    level: UserLevelData
    rank: int
    country: str | None
    age: str | None
    birthday: str | None
    invitations: int
    joined_at: datetime | None
    reward_level: int | None
    reward_name: str | None
    reward_emoji: str | None


class ProfileService:
    """Build profile data using Odinus' existing systems."""

    def __init__(self) -> None:
        self.level_service = LevelService()
        self.birthday_repository = BirthdayRepository()
        self.invitation_repository = InvitationRepository()
        self.reward_service = RewardService()

        self.birthday_repository.initialize()
        self.invitation_repository.initialize()

    def get_profile(
        self,
        guild: discord.Guild,
        member: discord.Member,
    ) -> ProfileData:
        """Collect all available profile information."""
        level_data = self.level_service.repository.get_user(
            guild.id,
            member.id,
        )

        rank = self._get_rank(
            guild.id,
            level_data,
        )

        country = self._get_country(member)
        age = self._get_age(member)
        birthday = self._get_birthday(
            guild.id,
            member.id,
        )

        invitations = (
            self.invitation_repository.user_invites(
                guild.id,
                member.id,
            )
        )

        reward_level, reward_name, reward_emoji = (
            self._get_current_reward(
                guild,
                member,
                level_data.level,
            )
        )

        return ProfileData(
            member=member,
            level=level_data,
            rank=rank,
            country=country,
            age=age,
            birthday=birthday,
            invitations=invitations,
            joined_at=member.joined_at,
            reward_level=reward_level,
            reward_name=reward_name,
            reward_emoji=reward_emoji,
        )

    def _get_rank(
        self,
        guild_id: int,
        user_data: UserLevelData,
    ) -> int:
        """Calculate ranking position using the same leaderboard order."""
        users = self.level_service.repository.get_leaderboard(
            guild_id=guild_id,
            limit=1_000_000,
            offset=0,
        )

        for position, user in enumerate(users, start=1):
            if user.user_id == user_data.user_id:
                return position

        return len(users) + 1

    @staticmethod
    def _get_country(
        member: discord.Member,
    ) -> str | None:
        """Find the configured country role."""
        country_roles = {
            role_name(
                emoji,
                country,
            ): country
            for _, emoji, country in COUNTRIES
        }

        for role in member.roles:
            country = country_roles.get(role.name)

            if country is not None:
                return country

        return None

    @staticmethod
    def _get_age(
        member: discord.Member,
    ) -> str | None:
        """Find the configured age role."""
        age_roles = {
            age_role_name(
                emoji,
                name,
            ): name
            for _, emoji, name in AGE_ROLES
        }

        for role in member.roles:
            age = age_roles.get(role.name)

            if age is not None:
                return age

        return None

    def _get_birthday(
        self,
        guild_id: int,
        user_id: int,
    ) -> str | None:
        """Return a member's registered birthday."""
        birthdays = self.birthday_repository.birthdays_in_guild(
            guild_id
        )

        birthday = next(
            (
                item
                for item in birthdays
                if item.user_id == user_id
            ),
            None,
        )

        if birthday is None:
            return None

        return (
            f"{birthday.day:02d}/"
            f"{birthday.month:02d}/"
            f"{birthday.year}"
        )

    def _get_current_reward(
        self,
        guild: discord.Guild,
        member: discord.Member,
        current_level: int,
    ) -> tuple[int | None, str | None, str | None]:
        """Find the highest configured reward role currently possessed."""
        rewards = self.reward_service.get_rewards(
            guild.id
        )

        owned_rewards = [
            reward
            for reward in rewards
            if reward.level <= current_level
            and member.get_role(reward.role_id) is not None
        ]

        if not owned_rewards:
            return None, None, None

        reward = max(
            owned_rewards,
            key=lambda item: item.level,
        )

        reward_name = reward.role_name
        reward_emoji = reward.emoji or None

        # Reward roles normally use this format:
        #
        # 『🍊』NIVEL 60
        #
        # Some existing rewards may have the emoji stored
        # directly in the role name while the database emoji
        # field is empty. Recover it from the role name.
        if (
            reward_name.startswith("『")
            and "』" in reward_name
        ):
            closing_bracket = reward_name.find("』")

            embedded_emoji = reward_name[
                1:closing_bracket
            ].strip()

            if not reward_emoji and embedded_emoji:
                reward_emoji = embedded_emoji

            reward_name = reward_name[
                closing_bracket + 1:
            ].strip()

        return (
            reward.level,
            reward_name,
            reward_emoji,
        )