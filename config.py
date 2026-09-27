"""Environment variable loading and validation for the bot."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class BotConfig:
    """Immutable, validated runtime configuration for the bot."""

    token: str
    prefix: str
    max_playlist_tracks: int
    cookies_file: str | None
    cookies_from_browser: str | None


DEFAULT_MAX_PLAYLIST_TRACKS = 25


def load_config() -> BotConfig:
    """Load and validate configuration from environment variables.

    Raises:
        RuntimeError: If a required environment variable is missing or empty.
    """
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and provide a valid bot token."
        )

    prefix = os.getenv("BOT_PREFIX", "!").strip() or "!"

    max_playlist_tracks_raw = os.getenv("MAX_PLAYLIST_TRACKS", "").strip()
    try:
        max_playlist_tracks = int(max_playlist_tracks_raw) if max_playlist_tracks_raw else DEFAULT_MAX_PLAYLIST_TRACKS
        if max_playlist_tracks <= 0:
            raise ValueError
    except ValueError:
        logging.getLogger(__name__).warning(
            "Invalid MAX_PLAYLIST_TRACKS value %r; falling back to %d.",
            max_playlist_tracks_raw,
            DEFAULT_MAX_PLAYLIST_TRACKS,
        )
        max_playlist_tracks = DEFAULT_MAX_PLAYLIST_TRACKS

    cookies_file = os.getenv("COOKIES_FILE", "").strip() or None
    if cookies_file and not Path(cookies_file).is_file():
        raise RuntimeError(
            f"COOKIES_FILE is set to '{cookies_file}' but no such file exists."
        )

    cookies_from_browser = os.getenv("COOKIES_FROM_BROWSER", "").strip() or None

    return BotConfig(
        token=token,
        prefix=prefix,
        max_playlist_tracks=max_playlist_tracks,
        cookies_file=cookies_file,
        cookies_from_browser=cookies_from_browser,
    )
