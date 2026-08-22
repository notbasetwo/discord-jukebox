"""Environment variable loading and validation for the bot."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class BotConfig:
    """Immutable, validated runtime configuration for the bot."""

    token: str
    prefix: str


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

    return BotConfig(token=token, prefix=prefix)
