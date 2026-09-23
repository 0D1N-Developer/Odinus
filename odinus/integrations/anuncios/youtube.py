"""YouTube integration for the Odinus announcement center."""

from __future__ import annotations

import logging

import aiohttp

from odinus.config import Settings
from odinus.integrations.anuncios.base import (
    AnnouncementEvent,
    AnnouncementIntegration,
)


LOGGER = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeIntegration(AnnouncementIntegration):
    """Discover new public videos from a YouTube channel."""

    platform = "youtube"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch_events(self) -> list[AnnouncementEvent]:
        """Return the latest videos from the configured YouTube channel."""
        channel = await self._get_channel()

        if channel is None:
            return []

        uploads_playlist_id = channel["uploads_playlist_id"]
        channel_title = channel["channel_title"]

        videos = await self._get_latest_videos(
            uploads_playlist_id
        )

        return [
            AnnouncementEvent(
                platform=self.platform,
                external_id=video["video_id"],
                event_type=self._detect_event_type(video),
                title=video["title"] or "Nuevo video",
                url=(
                    "https://www.youtube.com/watch?v="
                    f'{video["video_id"]}'
                ),
                description=video["description"],
                thumbnail_url=video["thumbnail_url"],
                published_at=video["published_at"],
                author_name=channel_title,
            )
            for video in videos
        ]

    async def _get_channel(
        self,
    ) -> dict[str, str] | None:
        """Get channel information and its uploads playlist."""
        params = {
            "part": "snippet,contentDetails",
            "id": self.settings.youtube_channel_id,
            "key": self.settings.youtube_api_key,
        }

        data = await self._request(
            "/channels",
            params,
        )

        if not data or not data.get("items"):
            LOGGER.warning(
                "YouTube channel not found: %s",
                self.settings.youtube_channel_id,
            )
            return None

        item = data["items"][0]

        try:
            channel_title = item["snippet"]["title"]
            uploads_playlist_id = item[
                "contentDetails"
            ]["relatedPlaylists"]["uploads"]
        except (KeyError, TypeError):
            LOGGER.error(
                "YouTube channel response is missing "
                "required information."
            )
            return None

        return {
            "channel_title": str(channel_title),
            "uploads_playlist_id": str(
                uploads_playlist_id
            ),
        }

    async def _get_latest_videos(
        self,
        playlist_id: str,
    ) -> list[dict[str, str | None]]:
        """Get the latest videos from the uploads playlist."""
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": "5",
            "key": self.settings.youtube_api_key,
        }

        data = await self._request(
            "/playlistItems",
            params,
        )

        if not data:
            return []

        videos: list[dict[str, str | None]] = []

        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            resource = snippet.get("resourceId", {})

            video_id = resource.get("videoId")

            if not video_id:
                continue

            thumbnails = snippet.get("thumbnails", {})

            thumbnail_url = None

            for thumbnail_name in (
                "maxres",
                "high",
                "medium",
                "default",
            ):
                thumbnail = thumbnails.get(thumbnail_name)

                if thumbnail:
                    thumbnail_url = thumbnail.get("url")

                    if thumbnail_url:
                        break

            videos.append(
                {
                    "video_id": video_id,
                    "title": snippet.get(
                        "title",
                        "Nuevo video",
                    ),
                    "description": snippet.get(
                        "description"
                    ),
                    "thumbnail_url": thumbnail_url,
                    "published_at": snippet.get(
                        "publishedAt"
                    ),
                    "live_broadcast_content": snippet.get(
                        "liveBroadcastContent"
                    ),
                }
            )

        return videos

    @staticmethod
    def _detect_event_type(
        video: dict[str, str | None],
    ) -> str:
        """Determine the YouTube event type."""
        broadcast_status = video.get(
            "live_broadcast_content"
        )

        if broadcast_status == "live":
            return "live"

        if broadcast_status == "upcoming":
            return "live_scheduled"

        title = str(
            video.get("title") or ""
        ).lower()

        if "short" in title:
            return "short"

        return "video"

    async def _request(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> dict | None:
        """Perform a request against the YouTube Data API."""
        url = f"{YOUTUBE_API_BASE}{endpoint}"

        try:
            timeout = aiohttp.ClientTimeout(total=30)

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
                            "YouTube API error %s: %s",
                            response.status,
                            data,
                        )
                        return None

                    return data

        except aiohttp.ClientError:
            LOGGER.exception(
                "Could not connect to the YouTube API."
            )
            return None

        except TimeoutError:
            LOGGER.exception(
                "YouTube API request timed out."
            )
            return None