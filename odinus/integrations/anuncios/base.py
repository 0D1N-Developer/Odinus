"""Base structures for Odinus announcement integrations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnnouncementEvent:
    """Normalized event received from an external platform."""

    platform: str
    external_id: str
    event_type: str
    title: str
    url: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    published_at: str | None = None
    author_name: str | None = None


class AnnouncementIntegration:
    """Base interface for external announcement integrations."""

    platform: str = "unknown"

    async def start(self) -> None:
        """Start the integration if it requires a background process."""

    async def stop(self) -> None:
        """Stop the integration if it requires a background process."""

    async def fetch_events(self) -> list[AnnouncementEvent]:
        """Return newly discovered events."""
        return []