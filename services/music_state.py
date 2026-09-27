"""Per-guild music controller: playback loop, FIFO queue, and voice state."""

from __future__ import annotations

import asyncio
import logging

import discord

from services.audio_source import AudioExtractionError, Track, resolve_track

logger = logging.getLogger(__name__)

# How long the player loop waits for a new track before disconnecting due to inactivity.
IDLE_TIMEOUT_SECONDS = 300


class GuildMusicState:
    """Owns the queue, voice client, and playback loop for a single guild.

    Each guild gets its own instance so playback, queues, and voice
    connections never interfere with one another across servers.
    """

    def __init__(self, guild: discord.Guild, bot_loop: asyncio.AbstractEventLoop) -> None:
        self.guild = guild
        self._loop = bot_loop

        self.voice_client: discord.VoiceClient | None = None
        self.queue: asyncio.Queue[Track] = asyncio.Queue()
        # Mirrors the contents of `queue` in order, for non-destructive display (e.g. `!queue`).
        self._queue_display: list[Track] = []

        self.current: Track | None = None
        self.text_channel: discord.abc.Messageable | None = None

        self._next_event = asyncio.Event()
        self._player_task: asyncio.Task[None] | None = None
        self._destroyed = False

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start the background playback loop if it is not already running."""
        if self._player_task is None or self._player_task.done():
            self._player_task = self._loop.create_task(self._player_loop())

    async def enqueue(self, track: Track) -> None:
        """Add a track to the FIFO queue."""
        await self.queue.put(track)
        self._queue_display.append(track)

    async def cleanup(self) -> None:
        """Stop playback, clear the queue, cancel the worker, and disconnect."""
        self._destroyed = True

        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._queue_display.clear()

        if self._player_task is not None:
            self._player_task.cancel()
            self._player_task = None

        if self.voice_client is not None and self.voice_client.is_connected():
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()
            await self.voice_client.disconnect(force=True)

        self.voice_client = None
        self.current = None

    # ------------------------------------------------------------------ #
    # Playback controls
    # ------------------------------------------------------------------ #

    def skip(self) -> bool:
        """Stop the current track, triggering the loop to advance. Returns success."""
        if self.voice_client is None or not (
            self.voice_client.is_playing() or self.voice_client.is_paused()
        ):
            return False
        self.voice_client.stop()
        return True

    def pause(self) -> bool:
        """Pause playback. Returns True if it was actually paused."""
        if self.voice_client is not None and self.voice_client.is_playing():
            self.voice_client.pause()
            return True
        return False

    def resume(self) -> bool:
        """Resume playback. Returns True if it was actually resumed."""
        if self.voice_client is not None and self.voice_client.is_paused():
            self.voice_client.resume()
            return True
        return False

    def upcoming(self, limit: int = 10) -> list[Track]:
        """Return up to ``limit`` tracks currently waiting in the queue."""
        return self._queue_display[:limit]

    # ------------------------------------------------------------------ #
    # Internal playback loop
    # ------------------------------------------------------------------ #

    async def _player_loop(self) -> None:
        """Continuously pop tracks off the queue and play them until idle/cancelled."""
        try:
            while True:
                self._next_event.clear()

                try:
                    track = await asyncio.wait_for(
                        self.queue.get(), timeout=IDLE_TIMEOUT_SECONDS
                    )
                except asyncio.TimeoutError:
                    logger.info(
                        "Guild %s idle for %ss, disconnecting.",
                        self.guild.id,
                        IDLE_TIMEOUT_SECONDS,
                    )
                    await self.cleanup()
                    return

                if self._queue_display:
                    self._queue_display.pop(0)

                if self.voice_client is None or not self.voice_client.is_connected():
                    logger.warning(
                        "Voice client disconnected for guild %s; dropping track '%s'.",
                        self.guild.id,
                        track.title,
                    )
                    continue

                if track.stream_url is None:
                    try:
                        track = await resolve_track(track)
                    except AudioExtractionError as exc:
                        logger.warning(
                            "Failed to resolve playlist track '%s' in guild %s: %s",
                            track.title,
                            self.guild.id,
                            exc,
                        )
                        if self.text_channel is not None:
                            await self.text_channel.send(f"Skipping unplayable track: **{track.title}**")
                        continue

                self.current = track

                try:
                    source = track.to_source()
                    self.voice_client.play(source, after=self._after_playback)
                except discord.ClientException:
                    logger.exception(
                        "Failed to start playback for '%s' in guild %s",
                        track.title,
                        self.guild.id,
                    )
                    self.current = None
                    continue

                await self._next_event.wait()
                self.current = None
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - keep the loop resilient
            logger.exception("Unexpected error in player loop for guild %s", self.guild.id)

    def _after_playback(self, error: Exception | None) -> None:
        """FFmpeg/discord.py callback fired from a non-async thread when a track ends."""
        if error is not None:
            logger.error("Playback error in guild %s: %s", self.guild.id, error)
        self._loop.call_soon_threadsafe(self._next_event.set)
