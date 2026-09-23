"""Twitch integration for the Odinus announcement center."""

from __future__ import annotations

import logging

import aiohttp

from odinus.config import Settings
from odinus.integrations.anuncios.base import (
    AnnouncementEvent,
    AnnouncementIntegration,
)


LOGGER = logging.getLogger(__name__)

TWITCH_API_BASE = "https://api.twitch.tv/helix"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"

TWITCH_ICON_URL = (
    "https://cdn.simpleicons.org/twitch/9146FF"
)


class TwitchIntegration(AnnouncementIntegration):
    """Discover live streams from a Twitch channel."""

    platform = "twitch"

    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings

        self._access_token: str | None = None
        self._streamer_id: str | None = None

    async def fetch_events(
        self,
    ) -> list[AnnouncementEvent]:
        """Return a new Twitch live event if the channel is live."""
        access_token = await self._get_access_token()

        if access_token is None:
            return []

        streamer = await self._get_streamer(
            access_token
        )

        if streamer is None:
            return []

        streamer_id = streamer["id"]

        stream = await self._get_stream(
            access_token,
            streamer_id,
        )

        if stream is None:
            return []

        game_icon_url = await self._get_game_icon(
            access_token,
            stream["game_id"],
        )

        return [
            AnnouncementEvent(
                platform=self.platform,
                external_id=stream["id"],
                event_type="live",
                title=(
                    stream["title"]
                    or "Stream en vivo"
                ),
                url=(
                    "https://www.twitch.tv/"
                    f'{stream["user_login"]}'
                ),
                description=(
                    f'{stream["game_name"]} • '
                    f'{stream["viewer_count"]} espectadores'
                    if stream["game_name"]
                    else None
                ),
                # SE CONSERVA: miniatura grande del stream.
                thumbnail_url=self._build_thumbnail_url(
                    stream
                ),
                # NUEVO: portada cuadrada del juego.
                image_url=game_icon_url,
                published_at=stream["started_at"],
                # NUEVO: avatar circular del canal.
                author_name=stream["user_name"],
                author_icon_url=(
                    streamer["profile_image_url"]
                    or None
                ),
                # NUEVO: logo de Twitch para el footer.
                platform_icon_url=TWITCH_ICON_URL,
            )
        ]

    async def _get_access_token(
        self,
    ) -> str | None:
        """Obtain an application access token from Twitch."""
        if self._access_token is not None:
            return self._access_token

        params = {
            "client_id": self.settings.twitch_client_id,
            "client_secret": (
                self.settings.twitch_client_secret
            ),
            "grant_type": "client_credentials",
        }

        try:
            timeout = aiohttp.ClientTimeout(
                total=30
            )

            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:
                async with session.post(
                    TWITCH_TOKEN_URL,
                    params=params,
                ) as response:
                    data = await response.json()

                    if response.status != 200:
                        LOGGER.error(
                            "Twitch OAuth error %s: %s",
                            response.status,
                            data,
                        )
                        return None

                    access_token = data.get(
                        "access_token"
                    )

                    if not access_token:
                        LOGGER.error(
                            "Twitch OAuth response did not "
                            "contain an access token."
                        )
                        return None

                    self._access_token = str(
                        access_token
                    )

                    return self._access_token

        except aiohttp.ClientError:
            LOGGER.exception(
                "Could not connect to Twitch OAuth."
            )
            return None

        except TimeoutError:
            LOGGER.exception(
                "Twitch OAuth request timed out."
            )
            return None

    async def _get_streamer(
        self,
        access_token: str,
    ) -> dict[str, str] | None:
        """Get the configured Twitch channel."""
        params = {
            "login": self._get_configured_channel()
        }

        data = await self._request(
            "/users",
            params,
            access_token,
        )

        if not data or not data.get("data"):
            LOGGER.warning(
                "Twitch channel not found: %s",
                self._get_configured_channel(),
            )
            return None

        user = data["data"][0]

        try:
            streamer = {
                "id": str(user["id"]),
                "login": str(user["login"]),
                "display_name": str(
                    user["display_name"]
                ),
                "profile_image_url": str(
                    user.get("profile_image_url")
                    or ""
                ),
            }
        except (KeyError, TypeError):
            LOGGER.error(
                "Twitch user response is missing "
                "required information."
            )
            return None

        self._streamer_id = streamer["id"]

        return streamer

    async def _get_stream(
        self,
        access_token: str,
        streamer_id: str,
    ) -> dict[str, str | int] | None:
        """Get the current live stream."""
        params = {
            "user_id": streamer_id,
        }

        data = await self._request(
            "/streams",
            params,
            access_token,
        )

        if not data or not data.get("data"):
            return None

        stream = data["data"][0]

        try:
            return {
                "id": str(stream["id"]),
                "user_id": str(
                    stream["user_id"]
                ),
                "user_login": str(
                    stream["user_login"]
                ),
                "user_name": str(
                    stream["user_name"]
                ),
                "game_id": str(
                    stream.get("game_id") or ""
                ),
                "game_name": str(
                    stream.get("game_name") or ""
                ),
                "title": str(
                    stream.get("title") or ""
                ),
                "viewer_count": int(
                    stream.get("viewer_count") or 0
                ),
                "started_at": str(
                    stream["started_at"]
                ),
                "thumbnail_url": str(
                    stream.get("thumbnail_url") or ""
                ),
            }

        except (KeyError, TypeError, ValueError):
            LOGGER.error(
                "Twitch stream response is missing "
                "required information."
            )
            return None

    async def _get_game_icon(
        self,
        access_token: str,
        game_id: str,
    ) -> str | None:
        """Get the Twitch game cover image."""
        if not game_id:
            return None

        params = {
            "id": game_id,
        }

        data = await self._request(
            "/games",
            params,
            access_token,
        )

        if not data or not data.get("data"):
            return None

        game = data["data"][0]

        box_art_url = str(
            game.get("box_art_url") or ""
        )

        if not box_art_url:
            return None

        return (
            box_art_url
            .replace("{width}", "285")
            .replace("{height}", "380")
        )

    async def _request(
        self,
        endpoint: str,
        params: dict[str, str],
        access_token: str,
    ) -> dict | None:
        """Perform an authenticated request against Twitch."""
        url = f"{TWITCH_API_BASE}{endpoint}"

        headers = {
            "Authorization": (
                f"Bearer {access_token}"
            ),
            "Client-Id": (
                self.settings.twitch_client_id
            ),
        }

        try:
            timeout = aiohttp.ClientTimeout(
                total=30
            )

            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                ) as response:
                    data = await response.json()

                    if response.status == 401:
                        LOGGER.warning(
                            "Twitch access token expired. "
                            "Refreshing token."
                        )

                        self._access_token = None

                        return None

                    if response.status != 200:
                        LOGGER.error(
                            "Twitch API error %s: %s",
                            response.status,
                            data,
                        )
                        return None

                    return data

        except aiohttp.ClientError:
            LOGGER.exception(
                "Could not connect to the Twitch API."
            )
            return None

        except TimeoutError:
            LOGGER.exception(
                "Twitch API request timed out."
            )
            return None

    @staticmethod
    def _build_thumbnail_url(
        stream: dict[str, str | int],
    ) -> str | None:
        """Build the current Twitch stream thumbnail URL."""
        thumbnail_url = str(
            stream.get("thumbnail_url") or ""
        )

        if not thumbnail_url:
            return None

        return (
            thumbnail_url
            .replace("{width}", "1280")
            .replace("{height}", "720")
        )

    def _get_configured_channel(self) -> str:
        """Return the configured Twitch channel."""
        return getattr(
            self.settings,
            "twitch_channel",
            "",
        ).strip()