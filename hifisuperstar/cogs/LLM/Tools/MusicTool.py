#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
from langchain_core.tools import StructuredTool


from hifisuperstar.core.Acl import Rule
from hifisuperstar.core.Acl.Acl import Acl
from hifisuperstar.core.Music.Player import Player
from hifisuperstar.core.Music.Playlist import Playlist
from hifisuperstar.core.Server.Server import connect_voice
from hifisuperstar.io.Logger import error


class _MessageAdapter:
    """Minimal adapter so that Player can be constructed from a discord.Message context."""

    def __init__(self, message):
        self.guild = message.guild
        self.user = message.author
        self.client = message._state._get_client()


async def _join_voice(message) -> bool:
    if message.author.voice is None:
        return False
    try:
        voice = await connect_voice(message.author.voice.channel)
    except (TimeoutError, discord.DiscordException, OSError) as exc:
        error(None, f"Could not join voice for LLM music tool: {exc}", message.guild)
        return False
    return voice.is_connected()


def create_music_tools(music_cog, message):
    """Return a list of StructuredTools that control the music player for the given message's guild."""
    guild_id = str(message.guild.id)
    denied = "Failed: you are not permitted to do that."

    def _allowed(rule) -> bool:
        # The slash commands enforce the ACL; the LLM must not be a way around it
        return Acl(message.guild.id).is_allowed(rule, message.author.id, True)

    def _get_player():
        if guild_id not in music_cog.players:
            music_cog.players[guild_id] = Player(
                _MessageAdapter(message), music_cog.config
            )
        return music_cog.players[guild_id]

    async def music_play(query: str) -> str:
        """Play a track or YouTube search query in the user's current voice channel."""
        if not _allowed(Rule.MUSIC_PLAY):
            return denied
        if not await _join_voice(message):
            return "Failed: could not join the user's voice channel."
        player = _get_player()
        track_info = await player.queue_track(query)
        if not track_info:
            return f"Failed to queue '{query}'."
        title = track_info["title"] if isinstance(track_info, dict) else query
        return f"Queued '{title}'."

    async def music_stop() -> str:
        """Stop music playback and clear the queue."""
        if not _allowed(Rule.MUSIC_STOP):
            return denied
        player = _get_player()
        await player.stop_track()
        player.get_playlist().clear()
        return "Playback stopped and queue cleared."

    def music_skip() -> str:
        """Skip the currently playing track."""
        if not _allowed(Rule.MUSIC_SKIP):
            return denied
        _get_player().skip_track()
        return "Skipped to the next track."

    def music_prev() -> str:
        """Go back to the previous track."""
        if not _allowed(Rule.MUSIC_SKIP):
            return denied
        _get_player().prev_track()
        return "Went back to the previous track."

    def music_get_queue() -> str:
        """Get the current music queue as a numbered list."""
        if not _allowed(Rule.MUSIC_QUEUE):
            return denied
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
        if not _allowed(Rule.MUSIC_QUEUE_REMOVE):
            return denied
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

    def music_list_playlists() -> str:
        """List the names of playlists saved for this server (separate from the current live queue)."""
        if not _allowed(Rule.MUSIC_PLAYLIST_LIST):
            return denied
        names = Playlist(message.guild.id).get_available_playlists()
        if not names:
            return "No saved playlists."
        return "\n".join(f"{i + 1}. {name}" for i, name in enumerate(names))

    def music_view_playlist(name: str) -> str:
        """View the tracks in a saved playlist by name (see music_list_playlists). Does not play it."""
        if not _allowed(Rule.MUSIC_PLAYLIST_LIST):
            return denied
        playlist = Playlist(message.guild.id, name)
        if not playlist.load_from_storage():
            return f"Failed: playlist '{name}' not found."
        tracks = playlist.get_tracks()
        if not tracks:
            return f"Playlist '{playlist.get_name()}' is empty."
        lines = [f"{i + 1}. {t['title']}" for i, t in enumerate(tracks)]
        return f"Playlist '{playlist.get_name()}' ({len(tracks)} track(s)):\n" + "\n".join(lines)

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
        StructuredTool.from_function(
            func=music_list_playlists,
            name="music_list_playlists",
            description="List the names of playlists saved for this server.",
        ),
        StructuredTool.from_function(
            func=music_view_playlist,
            name="music_view_playlist",
            description="View the tracks in a saved playlist by name, without playing it.",
        ),
    ]
