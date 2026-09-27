"""yt-dlp wrapper and FFmpeg audio stream extraction.

This module is responsible for turning a search query or URL into a
playable ``Track`` without ever blocking the asyncio event loop: all
yt-dlp calls are executed in a worker thread via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import logging
import re
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

# extract_flat avoids resolving every video's stream URL up front, so listing a playlist is fast.
YTDL_PLAYLIST_OPTIONS: dict[str, Any] = {
    **YTDL_FORMAT_OPTIONS,
    "noplaylist": False,
    "extract_flat": "in_playlist",
}

DEFAULT_MAX_PLAYLIST_TRACKS = 25

# Reconnect flags prevent abrupt cutoffs on flaky streams/connections.
FFMPEG_BEFORE_OPTIONS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
)
FFMPEG_OPTIONS: dict[str, str] = {
    "before_options": FFMPEG_BEFORE_OPTIONS,
    "options": "-vn",
}

_ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)
_ytdl_flat = yt_dlp.YoutubeDL(YTDL_PLAYLIST_OPTIONS)

# Matches yt-dlp's CLI syntax: BROWSER[+KEYRING][:PROFILE][::CONTAINER]
_COOKIES_FROM_BROWSER_RE = re.compile(
    r"""(?x)
    (?P<name>[^+:]+)
    (?:\s*\+\s*(?P<keyring>[^:]+))?
    (?:\s*:\s*(?!:)(?P<profile>.+?))?
    (?:\s*::\s*(?P<container>.+))?
    """
)


def _parse_cookies_from_browser(spec: str) -> tuple[str, str | None, str | None, str | None]:
    """Parse a ``BROWSER[+KEYRING][:PROFILE][::CONTAINER]`` string into yt-dlp's tuple form."""
    match = _COOKIES_FROM_BROWSER_RE.fullmatch(spec)
    if match is None:
        raise ValueError(f"Invalid COOKIES_FROM_BROWSER value: {spec!r}")
    name, keyring, profile, container = match.group("name", "keyring", "profile", "container")
    return name.lower(), profile, (keyring.upper() if keyring else None), container


def configure(cookies_file: str | None = None, cookies_from_browser: str | None = None) -> None:
    """Enable authenticated YouTube requests by attaching cookies to yt-dlp.

    Call this once at startup (before any tracks are resolved) so age-restricted,
    members-only, or otherwise sign-in-gated videos can be played.
    """
    global _ytdl, _ytdl_flat

    if cookies_file:
        YTDL_FORMAT_OPTIONS["cookiefile"] = cookies_file
        YTDL_PLAYLIST_OPTIONS["cookiefile"] = cookies_file
    if cookies_from_browser:
        browser_spec = _parse_cookies_from_browser(cookies_from_browser)
        YTDL_FORMAT_OPTIONS["cookiesfrombrowser"] = browser_spec
        YTDL_PLAYLIST_OPTIONS["cookiesfrombrowser"] = browser_spec

    _ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)
    _ytdl_flat = yt_dlp.YoutubeDL(YTDL_PLAYLIST_OPTIONS)


class AudioExtractionError(Exception):
    """Raised when yt-dlp fails to resolve a query into a playable stream."""


@dataclass(slots=True, kw_only=True)
class Track:
    """A single queued/playable track with metadata for display purposes.

    ``stream_url`` is None for playlist entries that haven't been resolved yet;
    see ``resolve_track``.
    """

    title: str
    stream_url: str | None = None
    webpage_url: str
    duration: int | None
    uploader: str | None
    requester: discord.abc.User

    def to_source(self) -> discord.PCMVolumeTransformer:
        """Build a fresh, playable Discord audio source for this track."""
        assert self.stream_url is not None, "Track must be resolved before playback."
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


def _extract_playlist_sync(url: str) -> list[dict[str, Any]]:
    """Blocking flat yt-dlp extraction. Must only be called from a worker thread."""
    info = _ytdl_flat.extract_info(url, download=False)
    if info is None:
        raise AudioExtractionError(f"No results found for '{url}'.")

    # A plain (non-playlist) video URL has no "entries"; treat it as a single-item playlist.
    entries = info.get("entries")
    if entries is None:
        entries = [info]

    entries = [entry for entry in entries if entry is not None]
    if not entries:
        raise AudioExtractionError(f"No playable videos found for '{url}'.")

    return entries


async def extract_playlist(
    url: str,
    requester: discord.abc.User,
    max_tracks: int = DEFAULT_MAX_PLAYLIST_TRACKS,
) -> list[Track]:
    """Resolve a playlist URL into a list of lazily-resolved ``Track`` objects.

    Each returned track has ``stream_url=None``; call ``resolve_track`` to fetch
    its real audio stream right before playback.

    Raises:
        AudioExtractionError: If the playlist cannot be resolved or is empty.
    """
    try:
        entries = await asyncio.to_thread(_extract_playlist_sync, url)
    except AudioExtractionError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        logger.warning("yt-dlp failed to extract playlist '%s': %s", url, exc)
        raise AudioExtractionError(f"Could not retrieve playlist for '{url}'.") from exc
    except Exception as exc:  # noqa: BLE001 - surface as a domain error
        logger.exception("Unexpected error extracting playlist '%s'", url)
        raise AudioExtractionError(f"Unexpected error resolving playlist '{url}'.") from exc

    tracks: list[Track] = []
    for entry in entries[:max_tracks]:
        webpage_url = entry.get("url") or entry.get("webpage_url")
        if not webpage_url:
            continue
        if not webpage_url.startswith("http"):
            webpage_url = f"https://www.youtube.com/watch?v={webpage_url}"

        tracks.append(
            Track(
                title=entry.get("title") or "Unknown title",
                webpage_url=webpage_url,
                duration=entry.get("duration"),
                uploader=entry.get("uploader"),
                requester=requester,
            )
        )

    if not tracks:
        raise AudioExtractionError(f"No playable videos found in '{url}'.")

    return tracks


async def resolve_track(track: Track) -> Track:
    """Return a fully resolved ``Track`` with a live stream URL.

    If ``track`` was already resolved (has a ``stream_url``), it is returned
    unchanged. Otherwise its ``webpage_url`` is re-extracted, refreshing both
    the stream URL and metadata.

    Raises:
        AudioExtractionError: If the track cannot be resolved to audio.
    """
    if track.stream_url is not None:
        return track
    return await extract_track(track.webpage_url, track.requester)
