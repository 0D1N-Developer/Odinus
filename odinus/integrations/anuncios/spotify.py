"""Spotify integration for the Odinus announcement center."""

from __future__ import annotations

import logging
import time

import aiohttp

from odinus.config import Settings
from odinus.integrations.anuncios.base import (
    AnnouncementEvent,
    AnnouncementIntegration,
)


LOGGER = logging.getLogger(__name__)

SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

SPOTIFY_ICON_URL = (
    "https://cdn.simpleicons.org/spotify/1DB954"
)

EP_MINIMUM_TRACKS = 4
EP_MAX_DURATION_MS = 20 * 60 * 1000


class SpotifyIntegration(AnnouncementIntegration):
    """Discover new releases from a Spotify artist."""

    platform = "spotify"

    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    async def fetch_events(
        self,
    ) -> list[AnnouncementEvent]:
        """Return the latest releases from the configured artist."""
        artist_id = (
            self.settings.spotify_artist_id
        )

        if not artist_id:
            LOGGER.error(
                "Spotify artist ID is not configured."
            )
            return []

        token = await self._get_access_token()

        if not token:
            return []

        artist = await self._get_artist(
            artist_id,
            token,
        )

        if not artist:
            return []

        albums = await self._get_artist_albums(
            artist_id,
            token,
        )

        if albums is None:
            return []

        artist_name = str(
            artist.get("name")
            or "Black Tibii"
        )

        artist_image_url = (
            self._extract_artist_image(
                artist
            )
        )

        events: list[AnnouncementEvent] = []

        for album in albums:
            album_id = album.get("id")

            if not album_id:
                continue

            album_artists = album.get(
                "artists",
                [],
            )

            if not self._belongs_to_artist(
                album_artists,
                artist_id,
            ):
                continue

            tracks = await self._get_album_tracks(
                str(album_id),
                token,
            )

            if tracks is None:
                LOGGER.warning(
                    "Could not retrieve tracks for "
                    "Spotify release %s.",
                    album_id,
                )
                continue

            event_type = self._classify_release(
                tracks
            )

            album_name = str(
                album.get("name")
                or "Nuevo lanzamiento"
            )

            title = self._build_title(
                artist_name,
                album_name,
                event_type,
            )

            description = (
                self._build_description(
                    artist_name,
                    album,
                    tracks,
                    event_type,
                )
            )

            cover_url = (
                self._extract_album_image(
                    album
                )
            )

            external_urls = album.get(
                "external_urls",
                {},
            )

            if not isinstance(
                external_urls,
                dict,
            ):
                external_urls = {}

            spotify_url = external_urls.get(
                "spotify"
            )

            release_date = album.get(
                "release_date"
            )

            events.append(
                AnnouncementEvent(
                    platform=self.platform,
                    external_id=str(album_id),
                    event_type=event_type,
                    title=title,
                    url=(
                        str(spotify_url)
                        if spotify_url
                        else None
                    ),
                    description=description,
                    thumbnail_url=cover_url,
                    image_url=(
                        artist_image_url
                        or None
                    ),
                    published_at=(
                        str(release_date)
                        if release_date
                        else None
                    ),
                    author_name=artist_name,
                    author_icon_url=(
                        artist_image_url
                        or None
                    ),
                    platform_icon_url=(
                        SPOTIFY_ICON_URL
                    ),
                )
            )

        events.sort(
            key=lambda event: (
                event.published_at or ""
            ),
            reverse=True,
        )

        return events

    async def _get_access_token(
        self,
    ) -> str | None:
        """Get a cached or new Spotify client-credentials token."""
        now = time.monotonic()

        if (
            self._access_token
            and now < self._token_expires_at
        ):
            return self._access_token

        try:
            timeout = aiohttp.ClientTimeout(
                total=30
            )

            auth = aiohttp.BasicAuth(
                self.settings.spotify_client_id,
                self.settings.spotify_client_secret,
            )

            data = {
                "grant_type": "client_credentials"
            }

            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:
                async with session.post(
                    SPOTIFY_TOKEN_URL,
                    auth=auth,
                    data=data,
                ) as response:
                    payload = await response.json()

                    if response.status != 200:
                        LOGGER.error(
                            "Spotify token error %s: %s",
                            response.status,
                            payload,
                        )
                        return None

                    access_token = payload.get(
                        "access_token"
                    )

                    expires_in = int(
                        payload.get(
                            "expires_in",
                            3600,
                        )
                    )

                    if not access_token:
                        LOGGER.error(
                            "Spotify token response "
                            "did not contain an access token."
                        )
                        return None

                    self._access_token = str(
                        access_token
                    )

                    self._token_expires_at = (
                        now
                        + max(
                            expires_in - 60,
                            60,
                        )
                    )

                    return self._access_token

        except aiohttp.ClientError:
            LOGGER.exception(
                "Could not connect to Spotify "
                "authentication API."
            )
            return None

        except (TypeError, ValueError):
            LOGGER.exception(
                "Invalid Spotify authentication response."
            )
            return None

    async def _get_artist(
        self,
        artist_id: str,
        token: str,
    ) -> dict | None:
        """Get Spotify artist information."""
        return await self._request(
            f"/artists/{artist_id}",
            token,
        )

    async def _get_artist_albums(
        self,
        artist_id: str,
        token: str,
    ) -> list[dict] | None:
        """Get the artist's albums and singles."""
        params = {
            "include_groups": "album,single",
            "limit": "20",
            "market": "MX",
        }

        data = await self._request(
            f"/artists/{artist_id}/albums",
            token,
            params=params,
        )

        if data is None:
            return None

        items = data.get(
            "items",
            [],
        )

        if not isinstance(
            items,
            list,
        ):
            return []

        return [
            item
            for item in items
            if isinstance(
                item,
                dict,
            )
        ]

    async def _get_album_tracks(
        self,
        album_id: str,
        token: str,
    ) -> list[dict] | None:
        """Get every track from a Spotify release."""
        params = {
            "limit": "50",
            "market": "MX",
        }

        data = await self._request(
            f"/albums/{album_id}/tracks",
            token,
            params=params,
        )

        if data is None:
            return None

        items = data.get(
            "items",
            [],
        )

        if not isinstance(
            items,
            list,
        ):
            return []

        return [
            item
            for item in items
            if isinstance(
                item,
                dict,
            )
        ]

    async def _request(
        self,
        endpoint: str,
        token: str,
        params: dict[str, str] | None = None,
    ) -> dict | None:
        """Perform an authenticated Spotify API request."""
        url = f"{SPOTIFY_API_BASE}{endpoint}"

        headers = {
            "Authorization": f"Bearer {token}",
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
                    headers=headers,
                    params=params,
                ) as response:
                    payload = await response.json()

                    if response.status != 200:
                        LOGGER.error(
                            "Spotify API error %s: %s",
                            response.status,
                            payload,
                        )
                        return None

                    return payload

        except aiohttp.ClientError:
            LOGGER.exception(
                "Could not connect to the Spotify API."
            )
            return None

        except (TypeError, ValueError):
            LOGGER.exception(
                "Invalid Spotify API response."
            )
            return None

    @staticmethod
    def _belongs_to_artist(
        artists: list,
        artist_id: str,
    ) -> bool:
        """Check whether the configured artist appears on the release."""
        if not isinstance(
            artists,
            list,
        ):
            return False

        for artist in artists:
            if not isinstance(
                artist,
                dict,
            ):
                continue

            if str(
                artist.get("id") or ""
            ) == artist_id:
                return True

        return False

    @staticmethod
    def _classify_release(
        tracks: list[dict],
    ) -> str:
        """
        Classify a Spotify release by track count
        and total duration.

        Rules:
        - 1 to 3 tracks -> single
        - 4+ tracks and under 20 minutes -> ep
        - 4+ tracks and 20 minutes or more -> album
        """
        track_count = len(tracks)

        if track_count <= 3:
            return "single"

        total_duration_ms = 0

        for track in tracks:
            duration_ms = track.get(
                "duration_ms",
                0,
            )

            try:
                total_duration_ms += int(
                    duration_ms
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

        if total_duration_ms < EP_MAX_DURATION_MS:
            return "ep"

        return "album"

    @staticmethod
    def _extract_artist_image(
        artist: dict,
    ) -> str | None:
        """Get the largest available artist image."""
        images = artist.get(
            "images",
            [],
        )

        if not isinstance(
            images,
            list,
        ):
            return None

        for image in images:
            if not isinstance(
                image,
                dict,
            ):
                continue

            url = image.get("url")

            if url:
                return str(url)

        return None

    @staticmethod
    def _extract_album_image(
        album: dict,
    ) -> str | None:
        """Get the largest available album cover."""
        images = album.get(
            "images",
            [],
        )

        if not isinstance(
            images,
            list,
        ):
            return None

        for image in images:
            if not isinstance(
                image,
                dict,
            ):
                continue

            url = image.get("url")

            if url:
                return str(url)

        return None

    @staticmethod
    def _build_title(
        artist_name: str,
        album_name: str,
        event_type: str,
    ) -> str:
        """Build the announcement title."""
        if event_type == "single":
            release_type = "sencillo"

        elif event_type == "ep":
            release_type = "EP"

        else:
            release_type = "álbum"

        return (
            f"{artist_name} lanzó un nuevo "
            f"{release_type}: {album_name}."
        )

    @staticmethod
    def _build_description(
        artist_name: str,
        album: dict,
        tracks: list[dict],
        event_type: str,
    ) -> str:
        """Build the release description."""
        album_name = str(
            album.get("name")
            or "Nuevo lanzamiento"
        )

        total_tracks = len(tracks)

        total_duration_ms = 0

        for track in tracks:
            duration_ms = track.get(
                "duration_ms",
                0,
            )

            try:
                total_duration_ms += int(
                    duration_ms
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

        total_seconds = (
            total_duration_ms // 1000
        )

        minutes = total_seconds // 60
        seconds = total_seconds % 60

        duration_text = (
            f"{minutes}:{seconds:02d}"
        )

        if event_type == "single":
            release_type = "Sencillo"

        elif event_type == "ep":
            release_type = "EP"

        else:
            release_type = "Álbum"

        release_date = str(
            album.get("release_date")
            or ""
        )

        parts = [
            f"{artist_name} lanzó "
            f"“{album_name}” en Spotify.",
            "",
            f"Tipo: {release_type}",
            f"Canciones: {total_tracks}",
            f"Duración total: {duration_text}",
        ]

        if release_date:
            parts.append(
                f"Fecha de lanzamiento: "
                f"{release_date}"
            )

        return "\n".join(parts)