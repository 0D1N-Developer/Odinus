"""Level reward persistence and business logic for Odinus."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class LevelReward:
    """A role reward configured for a specific level."""

    guild_id: int
    level: int
    role_id: int
    role_name: str
    emoji: str


class RewardRepository:
    """Handle persistence for level rewards."""

    def __init__(
        self,
        database_path: Path = Path("data") / "odinus.db",
    ) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        """Create the level rewards table if it does not exist."""
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS level_rewards (
                    guild_id INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    role_name TEXT NOT NULL,
                    emoji TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (guild_id, level)
                )
                """
            )

    def create_reward(
        self,
        guild_id: int,
        level: int,
        role_id: int,
        role_name: str,
        emoji: str,
    ) -> LevelReward:
        """Create a reward for a level."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO level_rewards (
                    guild_id,
                    level,
                    role_id,
                    role_name,
                    emoji
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    level,
                    role_id,
                    role_name,
                    emoji,
                ),
            )

        return LevelReward(
            guild_id=guild_id,
            level=level,
            role_id=role_id,
            role_name=role_name,
            emoji=emoji,
        )

    def update_reward(
        self,
        guild_id: int,
        level: int,
        role_id: int,
        role_name: str,
        emoji: str,
    ) -> LevelReward:
        """Update an existing level reward."""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE level_rewards
                SET
                    role_id = ?,
                    role_name = ?,
                    emoji = ?
                WHERE guild_id = ? AND level = ?
                """,
                (
                    role_id,
                    role_name,
                    emoji,
                    guild_id,
                    level,
                ),
            )

        return LevelReward(
            guild_id=guild_id,
            level=level,
            role_id=role_id,
            role_name=role_name,
            emoji=emoji,
        )

    def delete_reward(
        self,
        guild_id: int,
        level: int,
    ) -> bool:
        """Delete the reward configured for a level."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM level_rewards
                WHERE guild_id = ? AND level = ?
                """,
                (
                    guild_id,
                    level,
                ),
            )

        return cursor.rowcount > 0

    def get_reward(
        self,
        guild_id: int,
        level: int,
    ) -> LevelReward | None:
        """Return the reward configured for a level."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    guild_id,
                    level,
                    role_id,
                    role_name,
                    emoji
                FROM level_rewards
                WHERE guild_id = ? AND level = ?
                """,
                (
                    guild_id,
                    level,
                ),
            ).fetchone()

        if row is None:
            return None

        return LevelReward(
            guild_id=row[0],
            level=row[1],
            role_id=row[2],
            role_name=row[3],
            emoji=row[4],
        )

    def get_rewards(
        self,
        guild_id: int,
    ) -> list[LevelReward]:
        """Return all rewards configured for a server."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    guild_id,
                    level,
                    role_id,
                    role_name,
                    emoji
                FROM level_rewards
                WHERE guild_id = ?
                ORDER BY level ASC
                """,
                (guild_id,),
            ).fetchall()

        return [
            LevelReward(
                guild_id=row[0],
                level=row[1],
                role_id=row[2],
                role_name=row[3],
                emoji=row[4],
            )
            for row in rows
        ]

    def get_rewards_between_levels(
        self,
        guild_id: int,
        minimum_level: int,
        maximum_level: int,
    ) -> list[LevelReward]:
        """Return rewards inside an inclusive level range."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    guild_id,
                    level,
                    role_id,
                    role_name,
                    emoji
                FROM level_rewards
                WHERE guild_id = ?
                  AND level >= ?
                  AND level <= ?
                ORDER BY level ASC
                """,
                (
                    guild_id,
                    minimum_level,
                    maximum_level,
                ),
            ).fetchall()

        return [
            LevelReward(
                guild_id=row[0],
                level=row[1],
                role_id=row[2],
                role_name=row[3],
                emoji=row[4],
            )
            for row in rows
        ]

    def get_rewards_above_level(
        self,
        guild_id: int,
        level: int,
    ) -> list[LevelReward]:
        """Return rewards above a user's current level."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    guild_id,
                    level,
                    role_id,
                    role_name,
                    emoji
                FROM level_rewards
                WHERE guild_id = ?
                  AND level > ?
                ORDER BY level ASC
                """,
                (
                    guild_id,
                    level,
                ),
            ).fetchall()

        return [
            LevelReward(
                guild_id=row[0],
                level=row[1],
                role_id=row[2],
                role_name=row[3],
                emoji=row[4],
            )
            for row in rows
        ]

    def get_role_ids(
        self,
        guild_id: int,
    ) -> set[int]:
        """Return all Discord role IDs managed by Odinus."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role_id
                FROM level_rewards
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchall()

        return {int(row[0]) for row in rows}

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)


class RewardService:
    """Business logic for level rewards."""

    def __init__(
        self,
        repository: RewardRepository | None = None,
    ) -> None:
        self.repository = repository or RewardRepository()
        self.repository.initialize()

    def create_reward(
        self,
        guild_id: int,
        level: int,
        role_id: int,
        role_name: str,
        emoji: str = "",
    ) -> LevelReward:
        """Create a new level reward."""
        self._validate_level(level)

        role_name = role_name.strip()
        emoji = emoji.strip()

        if not role_name:
            raise ValueError("The role name cannot be empty.")

        if role_id <= 0:
            raise ValueError("The role ID must be valid.")

        if self.repository.get_reward(
            guild_id,
            level,
        ) is not None:
            raise ValueError(
                f"A reward already exists for level {level}."
            )

        return self.repository.create_reward(
            guild_id=guild_id,
            level=level,
            role_id=role_id,
            role_name=role_name,
            emoji=emoji,
        )

    def update_reward(
        self,
        guild_id: int,
        level: int,
        role_id: int,
        role_name: str,
        emoji: str = "",
    ) -> LevelReward:
        """Update an existing level reward."""
        self._validate_level(level)

        role_name = role_name.strip()
        emoji = emoji.strip()

        if not role_name:
            raise ValueError("The role name cannot be empty.")

        if role_id <= 0:
            raise ValueError("The role ID must be valid.")

        if self.repository.get_reward(
            guild_id,
            level,
        ) is None:
            raise ValueError(
                f"No reward exists for level {level}."
            )

        return self.repository.update_reward(
            guild_id=guild_id,
            level=level,
            role_id=role_id,
            role_name=role_name,
            emoji=emoji,
        )

    def delete_reward(
        self,
        guild_id: int,
        level: int,
    ) -> bool:
        """Delete a level reward."""
        self._validate_level(level)

        return self.repository.delete_reward(
            guild_id,
            level,
        )

    def get_reward(
        self,
        guild_id: int,
        level: int,
    ) -> LevelReward | None:
        """Return a reward for a specific level."""
        self._validate_level(level)

        return self.repository.get_reward(
            guild_id,
            level,
        )

    def get_rewards(
        self,
        guild_id: int,
    ) -> list[LevelReward]:
        """Return all configured rewards."""
        return self.repository.get_rewards(
            guild_id,
        )

    def get_rewards_between_levels(
        self,
        guild_id: int,
        minimum_level: int,
        maximum_level: int,
    ) -> list[LevelReward]:
        """Return rewards inside an inclusive level range."""
        self._validate_level(minimum_level)
        self._validate_level(maximum_level)

        if minimum_level > maximum_level:
            minimum_level, maximum_level = (
                maximum_level,
                minimum_level,
            )

        return self.repository.get_rewards_between_levels(
            guild_id=guild_id,
            minimum_level=minimum_level,
            maximum_level=maximum_level,
        )

    def get_rewards_above_level(
        self,
        guild_id: int,
        level: int,
    ) -> list[LevelReward]:
        """Return rewards above the specified level."""
        self._validate_level(level)

        return self.repository.get_rewards_above_level(
            guild_id=guild_id,
            level=level,
        )

    def get_managed_role_ids(
        self,
        guild_id: int,
    ) -> set[int]:
        """Return all role IDs managed by Odinus."""
        return self.repository.get_role_ids(
            guild_id,
        )

    @staticmethod
    def _validate_level(level: int) -> None:
        """Validate a configured reward level."""
        if level < 1:
            raise ValueError(
                "Reward levels must be 1 or higher."
            )