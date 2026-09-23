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

    twitch_client_id: str
    twitch_client_secret: str
    twitch_channel: str
    twitch_poll_interval: int

    instagram_user_id: str
    instagram_access_token: str
    instagram_poll_interval: int


def load_settings() -> Settings:
    """Load and validate settings from the local environment."""
    load_dotenv()

    token = os.getenv(
        "DISCORD_TOKEN",
        "",
    ).strip()

    youtube_api_key = os.getenv(
        "YOUTUBE_API_KEY",
        "",
    ).strip()

    youtube_channel_id = os.getenv(
        "YOUTUBE_CHANNEL_ID",
        "",
    ).strip()

    twitch_client_id = os.getenv(
        "TWITCH_CLIENT_ID",
        "",
    ).strip()

    twitch_client_secret = os.getenv(
        "TWITCH_CLIENT_SECRET",
        "",
    ).strip()

    twitch_channel = os.getenv(
        "TWITCH_CHANNEL",
        "",
    ).strip()

    instagram_user_id = os.getenv(
        "INSTAGRAM_USER_ID",
        "",
    ).strip()

    instagram_access_token = os.getenv(
        "INSTAGRAM_ACCESS_TOKEN",
        "",
    ).strip()

    youtube_poll_interval_raw = os.getenv(
        "YOUTUBE_POLL_INTERVAL",
        "300",
    ).strip()

    twitch_poll_interval_raw = os.getenv(
        "TWITCH_POLL_INTERVAL",
        "60",
    ).strip()

    instagram_poll_interval_raw = os.getenv(
        "INSTAGRAM_POLL_INTERVAL",
        "300",
    ).strip()

    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN is not configured. "
            "Add your bot token to the .env file."
        )

    if not youtube_api_key:
        raise RuntimeError(
            "YOUTUBE_API_KEY is not configured. "
            "Add your YouTube API key to the .env file."
        )

    if not youtube_channel_id:
        raise RuntimeError(
            "YOUTUBE_CHANNEL_ID is not configured. "
            "Add your YouTube channel ID to the .env file."
        )

    if not twitch_client_id:
        raise RuntimeError(
            "TWITCH_CLIENT_ID is not configured. "
            "Add your Twitch client ID to the .env file."
        )

    if not twitch_client_secret:
        raise RuntimeError(
            "TWITCH_CLIENT_SECRET is not configured. "
            "Add your Twitch client secret to the .env file."
        )

    if not twitch_channel:
        raise RuntimeError(
            "TWITCH_CHANNEL is not configured. "
            "Add your Twitch channel name to the .env file."
        )

    if not instagram_user_id:
        raise RuntimeError(
            "INSTAGRAM_USER_ID is not configured. "
            "Add your Instagram user ID to the .env file."
        )

    if not instagram_access_token:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN is not configured. "
            "Add your Instagram access token to the .env file."
        )

    try:
        youtube_poll_interval = int(
            youtube_poll_interval_raw
        )
    except ValueError as error:
        raise RuntimeError(
            "YOUTUBE_POLL_INTERVAL must be a valid integer "
            "in seconds."
        ) from error

    if youtube_poll_interval <= 0:
        raise RuntimeError(
            "YOUTUBE_POLL_INTERVAL must be greater than 0."
        )

    try:
        twitch_poll_interval = int(
            twitch_poll_interval_raw
        )
    except ValueError as error:
        raise RuntimeError(
            "TWITCH_POLL_INTERVAL must be a valid integer "
            "in seconds."
        ) from error

    if twitch_poll_interval <= 0:
        raise RuntimeError(
            "TWITCH_POLL_INTERVAL must be greater than 0."
        )

    try:
        instagram_poll_interval = int(
            instagram_poll_interval_raw
        )
    except ValueError as error:
        raise RuntimeError(
            "INSTAGRAM_POLL_INTERVAL must be a valid integer "
            "in seconds."
        ) from error

    if instagram_poll_interval <= 0:
        raise RuntimeError(
            "INSTAGRAM_POLL_INTERVAL must be greater than 0."
        )

    return Settings(
        discord_token=token,
        youtube_api_key=youtube_api_key,
        youtube_channel_id=youtube_channel_id,
        youtube_poll_interval=youtube_poll_interval,
        twitch_client_id=twitch_client_id,
        twitch_client_secret=twitch_client_secret,
        twitch_channel=twitch_channel,
        twitch_poll_interval=twitch_poll_interval,
        instagram_user_id=instagram_user_id,
        instagram_access_token=instagram_access_token,
        instagram_poll_interval=instagram_poll_interval,
    )