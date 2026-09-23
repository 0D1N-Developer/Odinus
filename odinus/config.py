"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Runtime settings required by Odinus."""

    discord_token: str
    youtube_api_key: str
    youtube_channel_id: str
    youtube_poll_interval: int


def load_settings() -> Settings:
    """Load and validate settings from the local environment."""
    load_dotenv()

    token = os.getenv("DISCORD_TOKEN", "").strip()
    youtube_api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    youtube_channel_id = os.getenv("YOUTUBE_CHANNEL_ID", "").strip()

    poll_interval_raw = os.getenv(
        "YOUTUBE_POLL_INTERVAL",
        "259200",
    ).strip()

    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN is not configured. Add your bot token to the .env file."
        )

    if not youtube_api_key:
        raise RuntimeError(
            "YOUTUBE_API_KEY is not configured. Add your YouTube API key to the .env file."
        )

    if not youtube_channel_id:
        raise RuntimeError(
            "YOUTUBE_CHANNEL_ID is not configured. Add your YouTube channel ID to the .env file."
        )

    try:
        youtube_poll_interval = int(poll_interval_raw)
    except ValueError as error:
        raise RuntimeError(
            "YOUTUBE_POLL_INTERVAL must be a valid integer in seconds."
        ) from error

    if youtube_poll_interval <= 0:
        raise RuntimeError(
            "YOUTUBE_POLL_INTERVAL must be greater than 0."
        )

    return Settings(
        discord_token=token,
        youtube_api_key=youtube_api_key,
        youtube_channel_id=youtube_channel_id,
        youtube_poll_interval=youtube_poll_interval,
    )