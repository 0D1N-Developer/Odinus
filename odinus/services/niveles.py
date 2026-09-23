"""XP and leveling service for Odinus."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


MAX_LEVEL = 1000

# XP awarded per valid message.
MIN_XP_PER_MESSAGE = 15
MAX_XP_PER_MESSAGE = 25

# Anti-spam cooldown in seconds.
XP_COOLDOWN_SECONDS = 60


@dataclass(slots=True)
class UserLevelData:
    """Current leveling data for a Discord user."""

    guild_id: int
    user_id: int
    total_xp: int
    level: int


class LevelRepository:
    """Handle persistence for the leveling system."""

    def __init__(
        self,
        database_path: Path = Path("data") / "odinus.db",
    ) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        """Create the leveling tables if they do not exist."""
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_levels (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    total_xp INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 0,
                    last_xp_at REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS level_settings (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1
                )
                """
            )

    def get_user(
        self,
        guild_id: int,
        user_id: int,
    ) -> UserLevelData:
        """Return a user's current leveling data."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT guild_id, user_id, total_xp, level
                FROM user_levels
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            ).fetchone()

        if row is None:
            return UserLevelData(
                guild_id=guild_id,
                user_id=user_id,
                total_xp=0,
                level=0,
            )

        return UserLevelData(
            guild_id=row[0],
            user_id=row[1],
            total_xp=row[2],
            level=row[3],
        )

    def get_leaderboard(
        self,
        guild_id: int,
        limit: int,
        offset: int,
    ) -> list[UserLevelData]:
        """Return users ordered by total XP descending."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT guild_id, user_id, total_xp, level
                FROM user_levels
                WHERE guild_id = ?
                ORDER BY total_xp DESC, user_id ASC
                LIMIT ? OFFSET ?
                """,
                (
                    guild_id,
                    limit,
                    offset,
                ),
            ).fetchall()

        return [
            UserLevelData(
                guild_id=row[0],
                user_id=row[1],
                total_xp=row[2],
                level=row[3],
            )
            for row in rows
        ]

    def count_users(
        self,
        guild_id: int,
    ) -> int:
        """Return the number of users with leveling data."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM user_levels
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        return int(row[0]) if row else 0

    def update_xp(
        self,
        guild_id: int,
        user_id: int,
        total_xp: int,
        new_level: int,
        current_time: float,
    ) -> UserLevelData:
        """Update a user's XP and level."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_levels (
                    guild_id,
                    user_id,
                    total_xp,
                    level,
                    last_xp_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    total_xp = excluded.total_xp,
                    level = excluded.level,
                    last_xp_at = excluded.last_xp_at
                """,
                (
                    guild_id,
                    user_id,
                    total_xp,
                    new_level,
                    current_time,
                ),
            )

        return UserLevelData(
            guild_id=guild_id,
            user_id=user_id,
            total_xp=total_xp,
            level=new_level,
        )

    def last_xp_at(
        self,
        guild_id: int,
        user_id: int,
    ) -> float:
        """Return the timestamp of the last XP award."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT last_xp_at
                FROM user_levels
                WHERE guild_id = ? AND user_id = ?
                """,
                (
                    guild_id,
                    user_id,
                ),
            ).fetchone()

        return float(row[0]) if row else 0.0

    def is_enabled(
        self,
        guild_id: int,
    ) -> bool:
        """
        Return whether automatic message XP is enabled.

        Servers without an existing configuration are considered
        enabled by default.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT enabled
                FROM level_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

            if row is None:
                connection.execute(
                    """
                    INSERT INTO level_settings (
                        guild_id,
                        enabled
                    )
                    VALUES (?, 1)
                    """,
                    (guild_id,),
                )

                return True

        return bool(row[0])

    def set_enabled(
        self,
        guild_id: int,
        enabled: bool,
    ) -> None:
        """Enable or disable automatic message XP for a guild."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO level_settings (
                    guild_id,
                    enabled
                )
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    enabled = excluded.enabled
                """,
                (
                    guild_id,
                    int(enabled),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)


class LevelService:
    """Business logic for XP and levels."""

    def __init__(
        self,
        repository: LevelRepository | None = None,
    ) -> None:
        self.repository = repository or LevelRepository()
        self.repository.initialize()

    def is_enabled(
        self,
        guild_id: int,
    ) -> bool:
        """Return whether automatic leveling is enabled."""
        return self.repository.is_enabled(guild_id)

    def enable(
        self,
        guild_id: int,
    ) -> None:
        """Enable automatic message XP."""
        self.repository.set_enabled(
            guild_id=guild_id,
            enabled=True,
        )

    def disable(
        self,
        guild_id: int,
    ) -> None:
        """Disable automatic message XP."""
        self.repository.set_enabled(
            guild_id=guild_id,
            enabled=False,
        )

    @staticmethod
    def xp_required_for_level(level: int) -> int:
        """
        Return the XP required to advance from one level to the next.

        This uses the documented Arcane exponential curve
        as the initial basis for Odinus.
        """
        if level < 0:
            level = 0

        return 5 * (level**2) + (level * 50) + 75

    def total_xp_for_level(
        self,
        target_level: int,
    ) -> int:
        """
        Return the minimum total XP required to reach a level.

        Level 0 requires 0 XP.
        """
        target_level = min(
            MAX_LEVEL,
            max(0, target_level),
        )

        total_xp = 0

        for level in range(target_level):
            total_xp += self.xp_required_for_level(level)

        return total_xp

    def level_from_xp(
        self,
        total_xp: int,
    ) -> int:
        """Calculate the current level from total accumulated XP."""
        if total_xp <= 0:
            return 0

        level = 0
        remaining_xp = total_xp

        while level < MAX_LEVEL:
            required = self.xp_required_for_level(level)

            if remaining_xp < required:
                break

            remaining_xp -= required
            level += 1

        return level

    def xp_progress(
        self,
        total_xp: int,
    ) -> tuple[int, int]:
        """
        Return current progress and required XP for the next level.

        Returns:
            (xp_into_current_level, xp_required_for_next_level)
        """
        if total_xp <= 0:
            return 0, self.xp_required_for_level(0)

        level = self.level_from_xp(total_xp)

        if level >= MAX_LEVEL:
            return 0, 0

        accumulated = self.total_xp_for_level(level)

        xp_into_level = total_xp - accumulated
        required = self.xp_required_for_level(level)

        return xp_into_level, required

    def add_xp(
        self,
        guild_id: int,
        user_id: int,
        xp_amount: int,
        current_time: float,
    ) -> tuple[UserLevelData, bool]:
        """
        Add XP to a user.

        Returns:
            (updated_data, leveled_up)
        """
        current = self.repository.get_user(
            guild_id,
            user_id,
        )

        xp_amount = max(0, xp_amount)

        new_total_xp = current.total_xp + xp_amount

        if current.level >= MAX_LEVEL:
            new_level = MAX_LEVEL
        else:
            new_level = self.level_from_xp(
                new_total_xp
            )

        updated = self.repository.update_xp(
            guild_id=guild_id,
            user_id=user_id,
            total_xp=new_total_xp,
            new_level=new_level,
            current_time=current_time,
        )

        leveled_up = new_level > current.level

        return updated, leveled_up

    def remove_xp(
        self,
        guild_id: int,
        user_id: int,
        xp_amount: int,
        current_time: float,
    ) -> tuple[UserLevelData, bool]:
        """
        Remove XP from a user.

        XP cannot go below zero.

        Returns:
            (updated_data, leveled_down)
        """
        current = self.repository.get_user(
            guild_id,
            user_id,
        )

        xp_amount = max(0, xp_amount)

        new_total_xp = max(
            0,
            current.total_xp - xp_amount,
        )

        new_level = self.level_from_xp(
            new_total_xp
        )

        updated = self.repository.update_xp(
            guild_id=guild_id,
            user_id=user_id,
            total_xp=new_total_xp,
            new_level=new_level,
            current_time=current_time,
        )

        leveled_down = new_level < current.level

        return updated, leveled_down

    def increase_level(
        self,
        guild_id: int,
        user_id: int,
        current_time: float,
    ) -> UserLevelData:
        """
        Increase a user's level by one.

        The user is moved to the minimum XP required
        for the next level.
        """
        current = self.repository.get_user(
            guild_id,
            user_id,
        )

        if current.level >= MAX_LEVEL:
            return current

        target_level = current.level + 1

        new_total_xp = self.total_xp_for_level(
            target_level
        )

        return self.repository.update_xp(
            guild_id=guild_id,
            user_id=user_id,
            total_xp=new_total_xp,
            new_level=target_level,
            current_time=current_time,
        )

    def decrease_level(
        self,
        guild_id: int,
        user_id: int,
        current_time: float,
    ) -> UserLevelData:
        """
        Decrease a user's level by one.

        The user is moved to the minimum XP required
        for the previous level.
        """
        current = self.repository.get_user(
            guild_id,
            user_id,
        )

        if current.level <= 0:
            return current

        target_level = current.level - 1

        new_total_xp = self.total_xp_for_level(
            target_level
        )

        return self.repository.update_xp(
            guild_id=guild_id,
            user_id=user_id,
            total_xp=new_total_xp,
            new_level=target_level,
            current_time=current_time,
        )

    def reset_user(
        self,
        guild_id: int,
        user_id: int,
        current_time: float,
    ) -> UserLevelData:
        """Reset a user's XP and level to zero."""
        return self.repository.update_xp(
            guild_id=guild_id,
            user_id=user_id,
            total_xp=0,
            new_level=0,
            current_time=current_time,
        )

    def can_receive_xp(
        self,
        guild_id: int,
        user_id: int,
        current_time: float,
    ) -> bool:
        """Check whether the user has passed the XP cooldown."""
        last_xp = self.repository.last_xp_at(
            guild_id,
            user_id,
        )

        return (
            current_time - last_xp
        ) >= XP_COOLDOWN_SECONDS

    def register_message(
        self,
        guild_id: int,
        user_id: int,
        xp_amount: int,
        current_time: float,
    ) -> tuple[UserLevelData, bool] | None:
        """
        Process a message for XP.

        Returns None when the user is still inside the cooldown.
        """
        if not self.can_receive_xp(
            guild_id=guild_id,
            user_id=user_id,
            current_time=current_time,
        ):
            return None

        return self.add_xp(
            guild_id=guild_id,
            user_id=user_id,
            xp_amount=xp_amount,
            current_time=current_time,
        )