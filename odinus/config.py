"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Runtime settings required by Odinus."""

    discord_token: str


def load_settings() -> Settings:
    """Load and validate settings from the local environment."""
    load_dotenv()

    token = os.getenv(
        "DISCORD_TOKEN",
        "",
    ).strip()

    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN is not configured. "
            "Add your bot token to the .env file."
        )

    return Settings(
        discord_token=token,
    )
