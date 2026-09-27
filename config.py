"""Environment variable loading and validation for the bot."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class BotConfig:
    """Immutable, validated runtime configuration for the bot."""

    token: str
    prefix: str
    max_playlist_tracks: int


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

    return BotConfig(token=token, prefix=prefix, max_playlist_tracks=max_playlist_tracks)
