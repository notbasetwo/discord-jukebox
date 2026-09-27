"""Main entry point: loads extensions and initializes the bot."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from config import load_config
from services import audio_source

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

INITIAL_EXTENSIONS: tuple[str, ...] = ("cogs.music",)


def build_bot(prefix: str) -> commands.Bot:
    """Construct the ``commands.Bot`` instance with the intents music requires."""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True

    return commands.Bot(command_prefix=prefix, intents=intents, help_command=commands.DefaultHelpCommand())


async def main() -> None:
    """Load configuration, register extensions, and run the bot."""
    config = load_config()
    audio_source.configure(config.cookies_file, config.cookies_from_browser)
    bot = build_bot(config.prefix)
    bot.config = config  # type: ignore[attr-defined]

    @bot.event
    async def on_ready() -> None:
        logger.info("Logged in as %s (id: %s)", bot.user, bot.user.id if bot.user else "unknown")

    async with bot:
        for extension in INITIAL_EXTENSIONS:
            await bot.load_extension(extension)
            logger.info("Loaded extension: %s", extension)

        await bot.start(config.token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down.")
