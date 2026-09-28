"""Moderation persistence and moderation helpers for Odinus."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ACTION_NAMES = {
    "delete": "Eliminar mensaje",
    "warn": "Advertir",
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

AUTOMOD_ACTIONS = {
    "delete": "Eliminar mensaje",
    "warn": "Advertir",
    "timeout": "Timeout",
}


BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "odinus.db"


# ---------------------------------------------------------------------------
# Default AutoMod configuration
# ---------------------------------------------------------------------------

DEFAULT_AUTOMOD_RULES = {
    "flood": {
        "enabled": True,
        "action": "delete",
        "timeout_seconds": 600,
        "threshold": 5,
        "window_seconds": 60,
    },
    "repeated_chars": {
        "enabled": True,
        "action": "delete",
        "timeout_seconds": 600,
        "threshold": 15,
        "window_seconds": 0,
    },
    "repeated_questions": {
        "enabled": True,
        "action": "delete",
        "timeout_seconds": 600,
        "threshold": 15,
        "window_seconds": 0,
    },
    "repeated_exclamations": {
        "enabled": True,
        "action": "delete",
        "timeout_seconds": 600,
        "threshold": 15,
        "window_seconds": 0,
    },
    "discord_invites": {
        "enabled": True,
        "action": "delete",
        "timeout_seconds": 600,
        "threshold": 1,
        "window_seconds": 0,
    },
    "suspicious_links": {
        "enabled": True,
        "action": "delete",
        "timeout_seconds": 600,
        "threshold": 1,
        "window_seconds": 0,
    },
    "mention_spam": {
        "enabled": True,
        "action": "delete",
        "timeout_seconds": 600,
        "threshold": 4,
        "window_seconds": 60,
    },
    "everyone_spam": {
        "enabled": True,
        "action": "delete",
        "timeout_seconds": 600,
        "threshold": 4,
        "window_seconds": 60,
    },
    "emoji_spam": {
        "enabled": True,
        "action": "delete",
        "timeout_seconds": 600,
        "threshold": 10,
        "window_seconds": 0,
    },
    "blocked_words": {
        "enabled": True,
        "action": "delete",
        "timeout_seconds": 600,
        "threshold": 1,
        "window_seconds": 0,
    },
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModerationSettings:
    guild_id: int
    log_channel_id: int | None
    enabled: bool


@dataclass(frozen=True)
class ModerationAction:
    id: int
    guild_id: int
    user_id: int
    moderator_id: int
    action: str
    reason: str
    duration: int | None
    created_at: str


@dataclass(frozen=True)
class AutomodRule:
    guild_id: int
    rule: str
    enabled: bool
    action: str
    timeout_seconds: int
    threshold: int
    window_seconds: int


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class ModerationRepository:
    """SQLite repository for moderation configuration and records."""

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS moderation_settings (
                    guild_id INTEGER PRIMARY KEY,
                    log_channel_id INTEGER,
                    enabled INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS moderation_ignored_channels (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, channel_id)
                );

                CREATE TABLE IF NOT EXISTS moderation_ignored_roles (
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, role_id)
                );

                CREATE TABLE IF NOT EXISTS moderation_warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    duration INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS moderation_automod_rules (
                    guild_id INTEGER NOT NULL,
                    rule TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    action TEXT NOT NULL DEFAULT 'delete',
                    timeout_seconds INTEGER NOT NULL DEFAULT 600,
                    threshold INTEGER NOT NULL DEFAULT 0,
                    window_seconds INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, rule)
                );

                CREATE TABLE IF NOT EXISTS moderation_blocked_words (
                    guild_id INTEGER NOT NULL,
                    word TEXT NOT NULL,
                    PRIMARY KEY (guild_id, word)
                );
                """
            )

            # ---------------------------------------------------------------
            # SQLite migration for installations created before threshold /
            # window_seconds existed.
            # ---------------------------------------------------------------

            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(moderation_automod_rules)"
                ).fetchall()
            }

            if "threshold" not in columns:
                connection.execute(
                    """
                    ALTER TABLE moderation_automod_rules
                    ADD COLUMN threshold INTEGER NOT NULL DEFAULT 0
                    """
                )

            if "window_seconds" not in columns:
                connection.execute(
                    """
                    ALTER TABLE moderation_automod_rules
                    ADD COLUMN window_seconds INTEGER NOT NULL DEFAULT 0
                    """
                )

            # Existing rules from the previous version had no threshold or
            # window configuration. Only migrate values still at zero.
            for rule_name, config in DEFAULT_AUTOMOD_RULES.items():
                connection.execute(
                    """
                    UPDATE moderation_automod_rules
                    SET threshold = ?,
                        window_seconds = ?
                    WHERE rule = ?
                      AND threshold = 0
                    """,
                    (
                        config["threshold"],
                        config["window_seconds"],
                        rule_name,
                    ),
                )

    # -----------------------------------------------------------------------
    # Settings
    # -----------------------------------------------------------------------

    def get_settings(self, guild_id: int) -> ModerationSettings:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT guild_id, log_channel_id, enabled
                FROM moderation_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        if row is None:
            return ModerationSettings(
                guild_id=guild_id,
                log_channel_id=None,
                enabled=False,
            )

        return ModerationSettings(
            guild_id=int(row["guild_id"]),
            log_channel_id=(
                int(row["log_channel_id"])
                if row["log_channel_id"] is not None
                else None
            ),
            enabled=bool(row["enabled"]),
        )

    def configure(
        self,
        guild_id: int,
        *,
        log_channel_id: int | None = None,
        enabled: bool | None = None,
    ) -> ModerationSettings:
        current = self.get_settings(guild_id)

        new_channel = (
            current.log_channel_id
            if log_channel_id is None
            else log_channel_id
        )

        new_enabled = (
            current.enabled
            if enabled is None
            else enabled
        )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO moderation_settings (
                    guild_id,
                    log_channel_id,
                    enabled
                )
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id)
                DO UPDATE SET
                    log_channel_id = excluded.log_channel_id,
                    enabled = excluded.enabled
                """,
                (
                    guild_id,
                    new_channel,
                    int(new_enabled),
                ),
            )

        return self.get_settings(guild_id)

    def set_log_channel(
        self,
        guild_id: int,
        channel_id: int | None,
    ) -> ModerationSettings:
        return self.configure(
            guild_id,
            log_channel_id=channel_id,
        )

    def set_enabled(
        self,
        guild_id: int,
        enabled: bool,
    ) -> ModerationSettings:
        return self.configure(
            guild_id,
            enabled=enabled,
        )

    # -----------------------------------------------------------------------
    # Ignored channels
    # -----------------------------------------------------------------------

    def get_ignored_channels(self, guild_id: int) -> set[int]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT channel_id
                FROM moderation_ignored_channels
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchall()

        return {
            int(row["channel_id"])
            for row in rows
        }

    def add_ignored_channel(
        self,
        guild_id: int,
        channel_id: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO moderation_ignored_channels (
                    guild_id,
                    channel_id
                )
                VALUES (?, ?)
                """,
                (guild_id, channel_id),
            )

    def remove_ignored_channel(
        self,
        guild_id: int,
        channel_id: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM moderation_ignored_channels
                WHERE guild_id = ?
                  AND channel_id = ?
                """,
                (guild_id, channel_id),
            )

    # -----------------------------------------------------------------------
    # Ignored roles
    # -----------------------------------------------------------------------

    def get_ignored_roles(self, guild_id: int) -> set[int]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role_id
                FROM moderation_ignored_roles
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchall()

        return {
            int(row["role_id"])
            for row in rows
        }

    def add_ignored_role(
        self,
        guild_id: int,
        role_id: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO moderation_ignored_roles (
                    guild_id,
                    role_id
                )
                VALUES (?, ?)
                """,
                (guild_id, role_id),
            )

    def remove_ignored_role(
        self,
        guild_id: int,
        role_id: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM moderation_ignored_roles
                WHERE guild_id = ?
                  AND role_id = ?
                """,
                (guild_id, role_id),
            )

    # -----------------------------------------------------------------------
    # Warnings
    # -----------------------------------------------------------------------

    def add_warning(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        reason: str,
    ) -> int:
        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO moderation_warnings (
                    guild_id,
                    user_id,
                    moderator_id,
                    reason,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    user_id,
                    moderator_id,
                    reason,
                    created_at,
                ),
            )

            return int(cursor.lastrowid)

    def get_warnings(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    guild_id,
                    user_id,
                    moderator_id,
                    reason,
                    created_at
                FROM moderation_warnings
                WHERE guild_id = ?
                  AND user_id = ?
                ORDER BY id DESC
                """,
                (guild_id, user_id),
            ).fetchall()

        return [dict(row) for row in rows]

    # -----------------------------------------------------------------------
    # Actions / modlogs
    # -----------------------------------------------------------------------

    def register_action(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        action: str,
        reason: str,
        duration: int | None = None,
    ) -> int:
        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO moderation_actions (
                    guild_id,
                    user_id,
                    moderator_id,
                    action,
                    reason,
                    duration,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    user_id,
                    moderator_id,
                    action,
                    reason,
                    duration,
                    created_at,
                ),
            )

            return int(cursor.lastrowid)

    def get_actions(
        self,
        guild_id: int,
        user_id: int | None = None,
        limit: int = 20,
    ) -> list[ModerationAction]:
        if user_id is None:
            query = """
                SELECT
                    id,
                    guild_id,
                    user_id,
                    moderator_id,
                    action,
                    reason,
                    duration,
                    created_at
                FROM moderation_actions
                WHERE guild_id = ?
                ORDER BY id DESC
                LIMIT ?
            """

            parameters = (
                guild_id,
                limit,
            )
        else:
            query = """
                SELECT
                    id,
                    guild_id,
                    user_id,
                    moderator_id,
                    action,
                    reason,
                    duration,
                    created_at
                FROM moderation_actions
                WHERE guild_id = ?
                  AND user_id = ?
                ORDER BY id DESC
                LIMIT ?
            """

            parameters = (
                guild_id,
                user_id,
                limit,
            )

        with self._connect() as connection:
            rows = connection.execute(
                query,
                parameters,
            ).fetchall()

        return [
            ModerationAction(
                id=int(row["id"]),
                guild_id=int(row["guild_id"]),
                user_id=int(row["user_id"]),
                moderator_id=int(row["moderator_id"]),
                action=str(row["action"]),
                reason=str(row["reason"]),
                duration=(
                    int(row["duration"])
                    if row["duration"] is not None
                    else None
                ),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    # -----------------------------------------------------------------------
    # AutoMod
    # -----------------------------------------------------------------------

    def ensure_default_automod_rules(
        self,
        guild_id: int,
    ) -> None:
        with self._connect() as connection:
            for rule, config in DEFAULT_AUTOMOD_RULES.items():
                connection.execute(
                    """
                    INSERT OR IGNORE INTO moderation_automod_rules (
                        guild_id,
                        rule,
                        enabled,
                        action,
                        timeout_seconds,
                        threshold,
                        window_seconds
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        rule,
                        int(config["enabled"]),
                        config["action"],
                        config["timeout_seconds"],
                        config["threshold"],
                        config["window_seconds"],
                    ),
                )

    def get_automod_rules(
        self,
        guild_id: int,
    ) -> list[AutomodRule]:
        self.ensure_default_automod_rules(guild_id)

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    guild_id,
                    rule,
                    enabled,
                    action,
                    timeout_seconds,
                    threshold,
                    window_seconds
                FROM moderation_automod_rules
                WHERE guild_id = ?
                ORDER BY rule
                """,
                (guild_id,),
            ).fetchall()

        return [
            AutomodRule(
                guild_id=int(row["guild_id"]),
                rule=str(row["rule"]),
                enabled=bool(row["enabled"]),
                action=str(row["action"]),
                timeout_seconds=int(row["timeout_seconds"]),
                threshold=max(1, int(row["threshold"])),
                window_seconds=max(0, int(row["window_seconds"])),
            )
            for row in rows
        ]

    def get_automod_rule(
        self,
        guild_id: int,
        rule: str,
    ) -> AutomodRule | None:
        self.ensure_default_automod_rules(guild_id)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    guild_id,
                    rule,
                    enabled,
                    action,
                    timeout_seconds,
                    threshold,
                    window_seconds
                FROM moderation_automod_rules
                WHERE guild_id = ?
                  AND rule = ?
                """,
                (guild_id, rule),
            ).fetchone()

        if row is None:
            return None

        return AutomodRule(
            guild_id=int(row["guild_id"]),
            rule=str(row["rule"]),
            enabled=bool(row["enabled"]),
            action=str(row["action"]),
            timeout_seconds=int(row["timeout_seconds"]),
            threshold=max(1, int(row["threshold"])),
            window_seconds=max(0, int(row["window_seconds"])),
        )

    def configure_automod_rule(
        self,
        guild_id: int,
        rule: str,
        *,
        enabled: bool | None = None,
        action: str | None = None,
        timeout_seconds: int | None = None,
        threshold: int | None = None,
        window_seconds: int | None = None,
    ) -> AutomodRule:
        current = self.get_automod_rule(
            guild_id,
            rule,
        )

        defaults = DEFAULT_AUTOMOD_RULES.get(
            rule,
            DEFAULT_AUTOMOD_RULES["blocked_words"],
        )

        current_enabled = (
            current.enabled
            if current is not None
            else bool(defaults["enabled"])
        )

        current_action = (
            current.action
            if current is not None
            else str(defaults["action"])
        )

        current_timeout = (
            current.timeout_seconds
            if current is not None
            else int(defaults["timeout_seconds"])
        )

        current_threshold = (
            current.threshold
            if current is not None
            else int(defaults["threshold"])
        )

        current_window = (
            current.window_seconds
            if current is not None
            else int(defaults["window_seconds"])
        )

        new_enabled = (
            current_enabled
            if enabled is None
            else bool(enabled)
        )

        new_action = (
            current_action
            if action is None
            else action
        )

        new_timeout = (
            current_timeout
            if timeout_seconds is None
            else max(1, min(int(timeout_seconds), 28 * 86400))
        )

        new_threshold = (
            current_threshold
            if threshold is None
            else max(1, min(int(threshold), 1000))
        )

        new_window = (
            current_window
            if window_seconds is None
            else max(0, min(int(window_seconds), 3600))
        )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO moderation_automod_rules (
                    guild_id,
                    rule,
                    enabled,
                    action,
                    timeout_seconds,
                    threshold,
                    window_seconds
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, rule)
                DO UPDATE SET
                    enabled = excluded.enabled,
                    action = excluded.action,
                    timeout_seconds = excluded.timeout_seconds,
                    threshold = excluded.threshold,
                    window_seconds = excluded.window_seconds
                """,
                (
                    guild_id,
                    rule,
                    int(new_enabled),
                    new_action,
                    new_timeout,
                    new_threshold,
                    new_window,
                ),
            )

        configured = self.get_automod_rule(
            guild_id,
            rule,
        )

        if configured is None:
            raise RuntimeError(
                "AutoMod rule could not be saved."
            )

        return configured

    # -----------------------------------------------------------------------
    # Blocked words
    # -----------------------------------------------------------------------

    def get_blocked_words(
        self,
        guild_id: int,
    ) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT word
                FROM moderation_blocked_words
                WHERE guild_id = ?
                ORDER BY word
                """,
                (guild_id,),
            ).fetchall()

        return {
            str(row["word"])
            for row in rows
        }

    def add_blocked_word(
        self,
        guild_id: int,
        word: str,
    ) -> None:
        word = word.strip().lower()

        if not word:
            return

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO moderation_blocked_words (
                    guild_id,
                    word
                )
                VALUES (?, ?)
                """,
                (
                    guild_id,
                    word,
                ),
            )

    def remove_blocked_word(
        self,
        guild_id: int,
        word: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM moderation_blocked_words
                WHERE guild_id = ?
                  AND word = ?
                """,
                (
                    guild_id,
                    word.strip().lower(),
                ),
            )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ModerationService:
    """Business logic for moderation."""

    def __init__(
        self,
        repository: ModerationRepository,
    ) -> None:
        self.repository = repository

    def is_ignored(
        self,
        message,
    ) -> bool:
        guild = message.guild

        if guild is None:
            return True

        settings = self.repository.get_settings(
            guild.id
        )

        if not settings.enabled:
            return True

        if message.channel.id in self.repository.get_ignored_channels(
            guild.id
        ):
            return True

        if hasattr(message.author, "roles"):
            ignored_roles = self.repository.get_ignored_roles(
                guild.id
            )

            if any(
                role.id in ignored_roles
                for role in message.author.roles
            ):
                return True

        return False

    def add_warning(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        reason: str,
    ) -> int:
        return self.repository.add_warning(
            guild_id,
            user_id,
            moderator_id,
            reason,
        )

    def register_action(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        action: str,
        reason: str,
        duration: int | None = None,
    ) -> int:
        return self.repository.register_action(
            guild_id,
            user_id,
            moderator_id,
            action,
            reason,
            duration,
        )

    def get_blocked_words(
        self,
        guild_id: int,
    ) -> set[str]:
        return self.repository.get_blocked_words(
            guild_id
        )


# ---------------------------------------------------------------------------
# Link detection
# ---------------------------------------------------------------------------

DISCORD_INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:discord\.gg|discord\.com/invite|discordapp\.com/invite)"
    r"/[A-Za-z0-9-]+",
    re.IGNORECASE,
)

URL_REGEX = re.compile(
    r"https?://[^\s<>()]+",
    re.IGNORECASE,
)

IP_URL_REGEX = re.compile(
    r"https?://"
    r"(?:\d{1,3}\.){3}\d{1,3}"
    r"(?::\d+)?(?:[/?#][^\s<>()]*)?",
    re.IGNORECASE,
)

PUNYCODE_REGEX = re.compile(
    r"(?:^|[./])xn--[a-z0-9-]+",
    re.IGNORECASE,
)

SUSPICIOUS_SHORTENERS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "is.gd",
    "cutt.ly",
    "shorturl.at",
    "rebrand.ly",
    "rb.gy",
    "ow.ly",
}


def contains_discord_invite(
    content: str,
) -> bool:
    return bool(
        DISCORD_INVITE_REGEX.search(content)
    )


def contains_suspicious_link(
    content: str,
) -> bool:
    for match in URL_REGEX.finditer(content):
        url = match.group(0)

        if IP_URL_REGEX.fullmatch(url):
            return True

        try:
            hostname = urlparse(url).hostname
        except ValueError:
            hostname = None

        if not hostname:
            continue

        hostname = hostname.lower().rstrip(".")

        if hostname in SUSPICIOUS_SHORTENERS:
            return True

        if PUNYCODE_REGEX.search(hostname):
            return True

    return False