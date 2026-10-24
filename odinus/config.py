"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Runtime settings required by Odinus."""

    discord_token: str
    minecraft_bridge_host: str = "127.0.0.1"
    minecraft_bridge_port: int = 8765
    minecraft_bridge_token: str = ""


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

    port_text = os.getenv(
        "MINECRAFT_BRIDGE_PORT",
        "8765",
    ).strip()

    try:
        port = int(port_text)
    except ValueError as error:
        raise RuntimeError(
            "MINECRAFT_BRIDGE_PORT must be a number."
        ) from error

    return Settings(
        discord_token=token,
        minecraft_bridge_host=os.getenv(
            "MINECRAFT_BRIDGE_HOST",
            "127.0.0.1",
        ).strip(),
        minecraft_bridge_port=port,
        minecraft_bridge_token=os.getenv(
            "MINECRAFT_BRIDGE_TOKEN",
            "",
        ).strip(),
    )
