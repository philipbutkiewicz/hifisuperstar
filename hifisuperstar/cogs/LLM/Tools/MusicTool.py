#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import asyncio

from langchain_core.tools import StructuredTool

from hifisuperstar.core.Music.Player import Player


class _MessageAdapter:
    """Minimal adapter so that Player can be constructed from a discord.Message context."""

    def __init__(self, message):
        self.guild = message.guild
        self.user = message.author
        self.client = message._state._get_client()


async def _join_voice(message) -> bool:
    if message.author.voice is None:
        return False
    channel = message.author.voice.channel
    if message.guild.voice_client is None:
        await channel.connect()
    else:
        await message.guild.voice_client.move_to(channel)
    return True


def create_music_tools(music_cog, message):
    """Return a list of StructuredTools that control the music player for the given message's guild."""
    guild_id = str(message.guild.id)

    def _get_player():
        if guild_id not in music_cog.players:
            music_cog.players[guild_id] = Player(
                _MessageAdapter(message), music_cog.config
            )
        return music_cog.players[guild_id]

    async def music_play(query: str) -> str:
        """Play a track or YouTube search query in the user's current voice channel."""
        if not await _join_voice(message):
            return "Failed: user is not in a voice channel."
        player = _get_player()
        track_info = await asyncio.to_thread(player.queue_track, query)
        if not track_info:
            return f"Failed to queue '{query}'."
        title = track_info["title"] if isinstance(track_info, dict) else query
        return f"Queued '{title}'."

    async def music_stop() -> str:
        """Stop music playback and clear the queue."""
        player = _get_player()
        await player.stop_track()
        player.get_playlist().clear()
        return "Playback stopped and queue cleared."

    def music_skip() -> str:
        """Skip the currently playing track."""
        _get_player().skip_track()
        return "Skipped to the next track."

    def music_prev() -> str:
        """Go back to the previous track."""
        _get_player().prev_track()
        return "Went back to the previous track."

    def music_get_queue() -> str:
        """Get the current music queue as a numbered list."""
        if guild_id not in music_cog.players:
            return "Nothing is in the queue."
        player = music_cog.players[guild_id]
        tracks = player.get_playlist().get_tracks()
        if not tracks:
            return "Nothing is in the queue."
        current = player.get_playlist().get_current_track()
        lines = []
        for i, t in enumerate(tracks):
            prefix = "▶ " if current and current["id"] == t["id"] else f"{i + 1}. "
            lines.append(f"{prefix}{t['title']}")
        return "\n".join(lines)

    def music_remove_track(index: int) -> str:
        """Remove a track from the queue by its 1-based index (see music_get_queue). Cannot remove the currently playing track."""
        if guild_id not in music_cog.players:
            return "Nothing is in the queue."
        player = music_cog.players[guild_id]
        playlist = player.get_playlist()
        tracks = playlist.get_tracks()
        if index < 1 or index > len(tracks):
            return f"Failed: index must be between 1 and {len(tracks)}."
        if index - 1 == playlist.get_current_track_index():
            return "Failed: cannot remove the currently playing track, skip it first."
        track = playlist.remove_track_at_index(index - 1)
        if not track:
            return "Failed to remove that track."
        return f"Removed '{track['title']}' from the queue."

    return [
        StructuredTool.from_function(
            coroutine=music_play,
            name="music_play",
            description="Play a track or YouTube search query. Joins the user's current voice channel. Queues the track if something is already playing.",
        ),
        StructuredTool.from_function(
            coroutine=music_stop,
            name="music_stop",
            description="Stop music playback and clear the queue.",
        ),
        StructuredTool.from_function(
            func=music_skip,
            name="music_skip",
            description="Skip the currently playing track.",
        ),
        StructuredTool.from_function(
            func=music_prev,
            name="music_prev",
            description="Go back to the previous track.",
        ),
        StructuredTool.from_function(
            func=music_get_queue,
            name="music_get_queue",
            description="Get the current music queue as a numbered list.",
        ),
        StructuredTool.from_function(
            func=music_remove_track,
            name="music_remove_track",
            description="Remove a track from the queue by its 1-based index. Cannot remove the currently playing track.",
        ),
    ]
