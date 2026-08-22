"""yt-dlp wrapper and FFmpeg audio stream extraction.

This module is responsible for turning a search query or URL into a
playable ``Track`` without ever blocking the asyncio event loop: all
yt-dlp calls are executed in a worker thread via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import discord
import yt_dlp

logger = logging.getLogger(__name__)

# Suppress noisy bug-report prompts from yt-dlp; we handle errors ourselves.
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ""

YTDL_FORMAT_OPTIONS: dict[str, Any] = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}

# Reconnect flags prevent abrupt cutoffs on flaky streams/connections.
FFMPEG_BEFORE_OPTIONS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
)
FFMPEG_OPTIONS: dict[str, str] = {
    "before_options": FFMPEG_BEFORE_OPTIONS,
    "options": "-vn",
}

_ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)


class AudioExtractionError(Exception):
    """Raised when yt-dlp fails to resolve a query into a playable stream."""


@dataclass(slots=True)
class Track:
    """A single queued/playable track with metadata for display purposes."""

    title: str
    stream_url: str
    webpage_url: str
    duration: int | None
    uploader: str | None
    requester: discord.abc.User

    def to_source(self) -> discord.PCMVolumeTransformer:
        """Build a fresh, playable Discord audio source for this track."""
        ffmpeg_audio = discord.FFmpegPCMAudio(self.stream_url, **FFMPEG_OPTIONS)
        return discord.PCMVolumeTransformer(ffmpeg_audio)

    @property
    def duration_display(self) -> str:
        """Human-readable ``MM:SS`` (or ``HH:MM:SS``) duration string."""
        if self.duration is None:
            return "Live/Unknown"
        minutes, seconds = divmod(int(self.duration), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:d}:{seconds:02d}"


def _extract_info_sync(query: str) -> dict[str, Any]:
    """Blocking yt-dlp extraction. Must only be called from a worker thread."""
    info = _ytdl.extract_info(query, download=False)
    if info is None:
        raise AudioExtractionError(f"No results found for '{query}'.")

    if "entries" in info:
        entries = [entry for entry in info["entries"] if entry is not None]
        if not entries:
            raise AudioExtractionError(f"No playable results found for '{query}'.")
        info = entries[0]

    return info


async def extract_track(query: str, requester: discord.abc.User) -> Track:
    """Resolve a search query or URL into a playable ``Track``.

    Runs the blocking yt-dlp extraction in a worker thread so the bot's
    gateway event loop is never blocked.

    Raises:
        AudioExtractionError: If the query cannot be resolved to audio.
    """
    try:
        info = await asyncio.to_thread(_extract_info_sync, query)
    except AudioExtractionError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        logger.warning("yt-dlp failed to extract '%s': %s", query, exc)
        raise AudioExtractionError(f"Could not retrieve audio for '{query}'.") from exc
    except Exception as exc:  # noqa: BLE001 - surface as a domain error
        logger.exception("Unexpected error extracting '%s'", query)
        raise AudioExtractionError(f"Unexpected error resolving '{query}'.") from exc

    stream_url = info.get("url")
    if not stream_url:
        raise AudioExtractionError(f"No playable stream found for '{query}'.")

    return Track(
        title=info.get("title") or "Unknown title",
        stream_url=stream_url,
        webpage_url=info.get("webpage_url") or query,
        duration=info.get("duration"),
        uploader=info.get("uploader"),
        requester=requester,
    )
