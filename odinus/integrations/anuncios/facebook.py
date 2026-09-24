"""Facebook integration for the Odinus announcement center."""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import aiohttp

from odinus.config import Settings
from odinus.integrations.anuncios.base import (
    AnnouncementEvent,
    AnnouncementIntegration,
)


LOGGER = logging.getLogger(__name__)

FACEBOOK_API_BASE = "https://graph.facebook.com"
FACEBOOK_WEB_BASE = "https://www.facebook.com"
FACEBOOK_ICON_URL = (
    "https://cdn.simpleicons.org/facebook/1877F2"
)


class FacebookIntegration(AnnouncementIntegration):
    """Discover new Facebook posts, Reels and videos."""

    platform = "facebook"

    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings

    async def fetch_events(
        self,
    ) -> list[AnnouncementEvent]:
        """Return the latest Facebook posts, Reels and videos."""
        page = await self._get_page()

        if page is None:
            return []

        posts = await self._get_latest_posts()
        videos = await self._get_latest_videos()

        if not posts and not videos:
            return []

        profile_picture_url = page[
            "profile_picture_url"
        ]

        events: list[AnnouncementEvent] = []

        # Prevent the same Facebook object from being returned
        # twice when it appears in both /posts and /videos.
        seen_ids: set[str] = set()

        for item in posts:
            external_id = self._build_external_id(
                item.get("id")
            )

            if not external_id:
                continue

            if external_id in seen_ids:
                continue

            seen_ids.add(external_id)

            post_image_url = (
                item.get("full_picture")
                or item.get("attachment_image_url")
            )

            events.append(
                AnnouncementEvent(
                    platform=self.platform,
                    external_id=external_id,
                    event_type="post",
                    title=(
                        "Black Tibii publicó una "
                        "nueva publicación."
                    ),
                    url=self._normalize_facebook_url(
                        item.get("permalink_url")
                    ),
                    description=item.get("message"),
                    thumbnail_url=post_image_url,
                    image_url=(
                        profile_picture_url or None
                    ),
                    published_at=item.get(
                        "created_time"
                    ),
                    author_name=page["name"],
                    author_icon_url=(
                        profile_picture_url or None
                    ),
                    platform_icon_url=(
                        FACEBOOK_ICON_URL
                    ),
                )
            )

        for item in videos:
            external_id = self._build_external_id(
                item.get("id")
            )

            if not external_id:
                continue

            if external_id in seen_ids:
                continue

            seen_ids.add(external_id)

            event_type = self._detect_video_type(
                item
            )

            events.append(
                AnnouncementEvent(
                    platform=self.platform,
                    external_id=external_id,
                    event_type=event_type,
                    title=self._build_title(
                        event_type
                    ),
                    url=self._normalize_facebook_url(
                        item.get("permalink_url")
                    ),
                    description=item.get(
                        "description"
                    ),
                    thumbnail_url=(
                        item.get("thumbnail_url")
                    ),
                    image_url=(
                        profile_picture_url or None
                    ),
                    published_at=item.get(
                        "created_time"
                    ),
                    author_name=page["name"],
                    author_icon_url=(
                        profile_picture_url or None
                    ),
                    platform_icon_url=(
                        FACEBOOK_ICON_URL
                    ),
                )
            )

        return events

    async def _get_page(
        self,
    ) -> dict[str, str] | None:
        """Get the configured Facebook page."""
        page_id = getattr(
            self.settings,
            "facebook_page_id",
            "",
        ).strip()

        if not page_id:
            LOGGER.error(
                "Facebook page ID is not configured."
            )
            return None

        params = {
            "fields": (
                "id,name,picture"
            ),
            "access_token": (
                self.settings.facebook_page_access_token
            ),
        }

        data = await self._request(
            f"/{page_id}",
            params,
        )

        if not data:
            return None

        try:
            picture = data.get(
                "picture",
                {},
            )

            picture_data = picture.get(
                "data",
                {},
            )

            return {
                "id": str(data["id"]),
                "name": str(
                    data.get("name")
                    or "Black Tibii"
                ),
                "profile_picture_url": str(
                    picture_data.get("url")
                    or ""
                ),
            }

        except (
            KeyError,
            TypeError,
            AttributeError,
        ):
            LOGGER.error(
                "Facebook page response is "
                "missing required information."
            )
            return None

    async def _get_latest_posts(
        self,
    ) -> list[dict[str, str | None]]:
        """Get the latest Facebook page posts."""
        page_id = getattr(
            self.settings,
            "facebook_page_id",
            "",
        ).strip()

        if not page_id:
            return []

        params = {
            "fields": (
                "id,message,created_time,"
                "permalink_url,full_picture,"
                "attachments"
            ),
            "limit": "10",
            "access_token": (
                self.settings.facebook_page_access_token
            ),
        }

        data = await self._request(
            f"/{page_id}/posts",
            params,
        )

        if not data:
            return []

        posts: list[dict[str, str | None]] = []

        for item in data.get("data", []):
            posts.append(
                {
                    "id": str(
                        item.get("id") or ""
                    ),
                    "message": item.get(
                        "message"
                    ),
                    "created_time": item.get(
                        "created_time"
                    ),
                    "permalink_url": item.get(
                        "permalink_url"
                    ),
                    "full_picture": item.get(
                        "full_picture"
                    ),
                    "attachment_image_url": (
                        self._extract_attachment_image(
                            item
                        )
                    ),
                }
            )

        return posts

    async def _get_latest_videos(
        self,
    ) -> list[dict[str, str | None]]:
        """Get the latest Facebook videos and Reels."""
        page_id = getattr(
            self.settings,
            "facebook_page_id",
            "",
        ).strip()

        if not page_id:
            return []

        params = {
            "fields": (
                "id,description,created_time,"
                "permalink_url,source,thumbnails"
            ),
            "limit": "10",
            "access_token": (
                self.settings.facebook_page_access_token
            ),
        }

        data = await self._request(
            f"/{page_id}/videos",
            params,
        )

        if not data:
            return []

        videos: list[dict[str, str | None]] = []

        for item in data.get("data", []):
            thumbnail_url = (
                self._extract_thumbnail(item)
            )

            videos.append(
                {
                    "id": str(
                        item.get("id") or ""
                    ),
                    "description": item.get(
                        "description"
                    ),
                    "created_time": item.get(
                        "created_time"
                    ),
                    "permalink_url": item.get(
                        "permalink_url"
                    ),
                    "source": item.get(
                        "source"
                    ),
                    "thumbnail_url": (
                        thumbnail_url
                    ),
                }
            )

        return videos

    @staticmethod
    def _build_external_id(
        value: str | None,
    ) -> str | None:
        """Return the original stable Facebook object ID."""
        if not value:
            return None

        external_id = str(value).strip()

        if not external_id:
            return None

        return external_id

    @staticmethod
    def _normalize_facebook_url(
        value: str | None,
    ) -> str | None:
        """Convert Facebook relative URLs to absolute URLs."""
        if not value:
            return None

        url = str(value).strip()

        if not url:
            return None

        if url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            return url

        if url.startswith("/"):
            return urljoin(
                FACEBOOK_WEB_BASE,
                url,
            )

        return urljoin(
            f"{FACEBOOK_WEB_BASE}/",
            url,
        )

    @staticmethod
    def _extract_attachment_image(
        item: dict,
    ) -> str | None:
        """Extract an image URL from a post attachment."""
        attachments = item.get(
            "attachments"
        )

        if not isinstance(attachments, dict):
            return None

        data = attachments.get("data")

        if not isinstance(data, list):
            return None

        for attachment in data:
            if not isinstance(attachment, dict):
                continue

            media = attachment.get("media")

            if not isinstance(media, dict):
                continue

            image = media.get("image")

            if not isinstance(image, dict):
                continue

            source = image.get("src")

            if source:
                return str(source)

        return None

    @staticmethod
    def _extract_thumbnail(
        item: dict,
    ) -> str | None:
        """Extract the best available video thumbnail."""
        thumbnails = item.get(
            "thumbnails"
        )

        if not isinstance(thumbnails, dict):
            return None

        data = thumbnails.get("data")

        if not isinstance(data, list):
            return None

        for thumbnail in data:
            if not isinstance(thumbnail, dict):
                continue

            uri = thumbnail.get("uri")

            if uri:
                return str(uri)

        return None

    @staticmethod
    def _detect_video_type(
        item: dict[str, str | None],
    ) -> str:
        """
        Determine the video announcement type.

        The current Meta response does not provide enough
        reliable information for a definitive Story/Reel
        distinction, so videos with media data continue to
        use the existing Reel classification.
        """
        source = str(
            item.get("source") or ""
        )

        thumbnail_url = str(
            item.get("thumbnail_url") or ""
        )

        if source or thumbnail_url:
            return "reel"

        return "video"

    @staticmethod
    def _build_title(
        event_type: str,
    ) -> str:
        """Build the announcement title."""
        if event_type == "reel":
            return (
                "Black Tibii publicó un nuevo Reel."
            )

        return (
            "Black Tibii publicó un nuevo video."
        )

    async def _request(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> dict | None:
        """Perform a request against the Facebook API."""
        url = f"{FACEBOOK_API_BASE}{endpoint}"

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
                            "Facebook API error %s: %s",
                            response.status,
                            data,
                        )
                        return None

                    return data

        except aiohttp.ClientError:
            LOGGER.exception(
                "Could not connect to the Facebook API."
            )
            return None

        except TimeoutError:
            LOGGER.exception(
                "Facebook API request timed out."
            )
            return None