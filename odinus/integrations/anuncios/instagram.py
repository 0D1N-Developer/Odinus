"""Instagram integration for the Odinus announcement center."""

from __future__ import annotations

import logging

import aiohttp

from odinus.config import Settings
from odinus.integrations.anuncios.base import (
    AnnouncementEvent,
    AnnouncementIntegration,
)


LOGGER = logging.getLogger(__name__)

INSTAGRAM_API_BASE = "https://graph.instagram.com"
INSTAGRAM_ICON_URL = (
    "https://cdn.simpleicons.org/instagram/E4405F"
)


class InstagramIntegration(AnnouncementIntegration):
    """Discover new Instagram posts and Reels."""

    platform = "instagram"

    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings

    async def fetch_events(
        self,
    ) -> list[AnnouncementEvent]:
        """Return the latest Instagram posts and Reels."""
        profile = await self._get_profile()

        if profile is None:
            return []

        media = await self._get_latest_media()

        if not media:
            return []

        profile_picture_url = profile[
            "profile_picture_url"
        ]

        return [
            AnnouncementEvent(
                platform=self.platform,
                external_id=item["id"],
                event_type=self._detect_event_type(
                    item["media_type"]
                ),
                title=self._build_title(
                    item["media_type"]
                ),
                url=item["permalink"],
                description=item["caption"],
                # Miniatura grande.
                thumbnail_url=(
                    item["thumbnail_url"]
                    or item["media_url"]
                ),
                # Imagen cuadrada superior.
                image_url=profile_picture_url or None,
                published_at=item["timestamp"],
                # Avatar circular.
                author_name=profile["name"],
                author_icon_url=(
                    profile_picture_url or None
                ),
                # Logo de Instagram.
                platform_icon_url=INSTAGRAM_ICON_URL,
            )
            for item in media
            if item.get("id")
        ]

    async def _get_profile(
        self,
    ) -> dict[str, str] | None:
        """Get the configured Instagram profile."""
        user_id = getattr(
            self.settings,
            "instagram_user_id",
            "",
        ).strip()

        if not user_id:
            LOGGER.error(
                "Instagram user ID is not configured."
            )
            return None

        params = {
            "fields": (
                "id,username,name,"
                "profile_picture_url"
            ),
            "access_token": (
                self.settings.instagram_access_token
            ),
        }

        data = await self._request(
            f"/{user_id}",
            params,
        )

        if not data:
            return None

        try:
            return {
                "id": str(data["id"]),
                "username": str(
                    data.get("username") or ""
                ),
                "name": str(
                    data.get("name")
                    or data.get("username")
                    or "Instagram"
                ),
                "profile_picture_url": str(
                    data.get("profile_picture_url")
                    or ""
                ),
            }

        except (KeyError, TypeError):
            LOGGER.error(
                "Instagram profile response is "
                "missing required information."
            )
            return None

    async def _get_latest_media(
        self,
    ) -> list[dict[str, str | None]]:
        """Get the latest Instagram media."""
        user_id = getattr(
            self.settings,
            "instagram_user_id",
            "",
        ).strip()

        if not user_id:
            return []

        params = {
            "fields": (
                "id,caption,media_type,media_url,"
                "thumbnail_url,permalink,timestamp,"
                "username"
            ),
            "limit": "10",
            "access_token": (
                self.settings.instagram_access_token
            ),
        }

        data = await self._request(
            f"/{user_id}/media",
            params,
        )

        if not data:
            return []

        media: list[dict[str, str | None]] = []

        for item in data.get("data", []):
            media_type = str(
                item.get("media_type") or ""
            ).upper()

            if media_type not in {
                "IMAGE",
                "CAROUSEL_ALBUM",
                "VIDEO",
            }:
                continue

            media.append(
                {
                    "id": str(
                        item.get("id") or ""
                    ),
                    "caption": item.get(
                        "caption"
                    ),
                    "media_type": media_type,
                    "media_url": item.get(
                        "media_url"
                    ),
                    "thumbnail_url": item.get(
                        "thumbnail_url"
                    ),
                    "permalink": item.get(
                        "permalink"
                    ),
                    "timestamp": item.get(
                        "timestamp"
                    ),
                    "username": item.get(
                        "username"
                    ),
                }
            )

        return media

    @staticmethod
    def _detect_event_type(
        media_type: str | None,
    ) -> str:
        """Determine the Instagram event type."""
        if media_type == "VIDEO":
            return "reel"

        if media_type == "CAROUSEL_ALBUM":
            return "post"

        return "post"

    @staticmethod
    def _build_title(
        media_type: str | None,
    ) -> str:
        """Build the announcement title."""
        if media_type == "VIDEO":
            return "Black Tibii publicó un nuevo Reel."

        return "Black Tibii publicó una nueva publicación."

    async def _request(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> dict | None:
        """Perform a request against the Instagram API."""
        url = f"{INSTAGRAM_API_BASE}{endpoint}"

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
                ) as response:
                    data = await response.json()

                    if response.status != 200:
                        LOGGER.error(
                            "Instagram API error %s: %s",
                            response.status,
                            data,
                        )
                        return None

                    return data

        except aiohttp.ClientError:
            LOGGER.exception(
                "Could not connect to the Instagram API."
            )
            return None

        except TimeoutError:
            LOGGER.exception(
                "Instagram API request timed out."
            )
            return None