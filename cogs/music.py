"""Music command cog: play, skip, queue, stop/leave, pause, resume."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from services.audio_source import AudioExtractionError, extract_track
from services.music_state import GuildMusicState

logger = logging.getLogger(__name__)


class MusicCog(commands.Cog, name="Music"):
    """Voice channel music playback backed by yt-dlp and FFmpeg."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._states: dict[int, GuildMusicState] = {}

    def _get_state(self, guild: discord.Guild) -> GuildMusicState:
        """Get or lazily create the ``GuildMusicState`` for a guild."""
        state = self._states.get(guild.id)
        if state is None:
            state = GuildMusicState(guild, self.bot.loop)
            self._states[guild.id] = state
        return state

    async def cog_unload(self) -> None:
        """Ensure every guild's playback is cleanly stopped on cog reload/unload."""
        for state in list(self._states.values()):
            await state.cleanup()
        self._states.clear()

    # ------------------------------------------------------------------ #
    # Voice connection helpers
    # ------------------------------------------------------------------ #

    async def _ensure_voice(
        self, ctx: commands.Context[commands.Bot]
    ) -> discord.VoiceClient | None:
        """Join (or move to) the invoker's voice channel. Returns None on failure."""
        author = ctx.author
        if not isinstance(author, discord.Member) or author.voice is None or author.voice.channel is None:
            await ctx.send("You need to be in a voice channel to use this command.")
            return None

        target_channel = author.voice.channel
        voice_client = ctx.guild.voice_client if ctx.guild else None

        if voice_client is None:
            try:
                voice_client = await target_channel.connect()
            except discord.ClientException as exc:
                logger.exception("Failed to connect to voice channel")
                await ctx.send(f"Could not join your voice channel: {exc}")
                return None
        elif voice_client.channel != target_channel:
            await voice_client.move_to(target_channel)

        assert isinstance(voice_client, discord.VoiceClient)
        return voice_client

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx: commands.Context[commands.Bot], *, query: str) -> None:
        """Join your voice channel, resolve the query/URL, and enqueue it for playback."""
        if ctx.guild is None:
            return

        voice_client = await self._ensure_voice(ctx)
        if voice_client is None:
            return

        state = self._get_state(ctx.guild)
        state.text_channel = ctx.channel
        state.voice_client = voice_client
        state.start()

        async with ctx.typing():
            try:
                track = await extract_track(query, ctx.author)
            except AudioExtractionError as exc:
                await ctx.send(f"Could not add that to the queue: {exc}")
                return

        await state.enqueue(track)
        await ctx.send(f"Queued **{track.title}** ({track.duration_display})")

    @commands.command(name="skip")
    async def skip(self, ctx: commands.Context[commands.Bot]) -> None:
        """Skip the currently playing track and advance to the next one."""
        if ctx.guild is None:
            return

        state = self._states.get(ctx.guild.id)
        if state is None or not state.skip():
            await ctx.send("Nothing is currently playing.")
            return

        await ctx.send("Skipped.")

    @commands.command(name="queue", aliases=["q"])
    async def queue(self, ctx: commands.Context[commands.Bot]) -> None:
        """Display the currently playing song and the next 10 upcoming songs."""
        if ctx.guild is None:
            return

        state = self._states.get(ctx.guild.id)
        if state is None or (state.current is None and not state.upcoming()):
            await ctx.send("The queue is empty.")
            return

        lines: list[str] = []
        if state.current is not None:
            lines.append(f"**Now Playing:** {state.current.title} ({state.current.duration_display})")
        else:
            lines.append("**Now Playing:** Nothing")

        upcoming = state.upcoming(10)
        if upcoming:
            lines.append("\n**Up Next:**")
            lines.extend(
                f"{index}. {track.title} ({track.duration_display})"
                for index, track in enumerate(upcoming, start=1)
            )

        await ctx.send("\n".join(lines))

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context[commands.Bot]) -> None:
        """Clear the queue, stop audio, cancel the worker task, and disconnect."""
        if ctx.guild is None:
            return

        state = self._states.pop(ctx.guild.id, None)
        if state is None:
            await ctx.send("I'm not connected to a voice channel.")
            return

        await state.cleanup()
        await ctx.send("Stopped playback and left the voice channel.")

    @commands.command(name="leave", aliases=["disconnect"])
    async def leave(self, ctx: commands.Context[commands.Bot]) -> None:
        """Alias for `stop`: leave the voice channel and clean up."""
        await self.stop(ctx)

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context[commands.Bot]) -> None:
        """Pause the currently playing track."""
        if ctx.guild is None:
            return

        state = self._states.get(ctx.guild.id)
        if state is None or not state.pause():
            await ctx.send("Nothing is currently playing.")
            return

        await ctx.send("Paused.")

    @commands.command(name="resume")
    async def resume(self, ctx: commands.Context[commands.Bot]) -> None:
        """Resume a paused track."""
        if ctx.guild is None:
            return

        state = self._states.get(ctx.guild.id)
        if state is None or not state.resume():
            await ctx.send("Nothing is currently paused.")
            return

        await ctx.send("Resumed.")

    @play.error
    async def play_error(
        self, ctx: commands.Context[commands.Bot], error: commands.CommandError
    ) -> None:
        """Handle missing query argument for `play`."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!play <song name or URL>`")
        else:
            logger.exception("Unhandled error in play command", exc_info=error)
            await ctx.send(f"An unexpected error occurred: {error}")

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Clean up state if the bot is disconnected/kicked from a voice channel."""
        if self.bot.user is None or member.id != self.bot.user.id:
            return
        if before.channel is not None and after.channel is None:
            guild = before.channel.guild
            state = self._states.pop(guild.id, None)
            if state is not None:
                await state.cleanup()


async def setup(bot: commands.Bot) -> None:
    """Entry point used by `bot.load_extension('cogs.music')`."""
    await bot.add_cog(MusicCog(bot))
