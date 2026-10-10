#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import asyncio

import discord
from langchain_core.tools import StructuredTool

from hifisuperstar.core.Acl import Rule
from hifisuperstar.core.Acl.Acl import Acl
from hifisuperstar.core.Music.Player import Player
from hifisuperstar.core.Music.Playlist import Playlist
from hifisuperstar.core.Server.Server import connect_voice
from hifisuperstar.io.Logger import error, info

_MAX_BATCH = 50
_background_tasks = set()
_batch_locks = {}


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

    async def music_play_many(queries: list[str]) -> str:
        """Queue several songs in the background."""
        if not _allowed(Rule.MUSIC_PLAY):
            return denied
        queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
        if not queries:
            return "Failed: no songs were given."
        queries = queries[:_MAX_BATCH]
        if not await _join_voice(message):
            return "Failed: could not join the user's voice channel."
        player = _get_player()

        # Looking up and caching every track takes a long time: queue them in the background
        # and let the model answer right away.
        task = asyncio.create_task(_queue_batch(player, queries))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return (
            f"Started queueing {len(queries)} song(s) in the background; they will show up in the "
            "queue as they are found (the first one starts playing as soon as it is ready). "
            "Do not wait for them, just tell the user."
        )

    async def _queue_batch(player, queries):
        lock = _batch_locks.setdefault(guild_id, asyncio.Lock())
        stop_count = player.stop_count
        failed = []
        try:
            async with lock:
                for query in queries:
                    if player.stop_count != stop_count:
                        info(None, "Batch queueing cancelled by a stop", message.guild)
                        return
                    try:
                        queued = await player.queue_track(query)
                    except Exception as exc:
                        error(None, f"Batch queue of '{query}' failed: {exc}", message.guild)
                        queued = False
                    if not queued:
                        failed.append(query)
        except Exception as exc:
            error(None, f"Batch queueing crashed: {exc}", message.guild)
            return

        info(
            None,
            f"Batch queueing finished: {len(queries) - len(failed)}/{len(queries)} queued",
            message.guild,
        )
        if failed:
            try:
                await message.channel.send(
                    "Couldn't queue: " + "; ".join(failed[:10])[:1500],
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                pass

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

    def music_set_shuffle(enabled: bool) -> str:
        """Turn shuffle mode on or off."""
        if not _allowed(Rule.MUSIC_SET_SHUFFLE):
            return denied
        shuffle = _get_player().set_shuffle(enabled)
        return f"Shuffle is now {'on' if shuffle else 'off'}."

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
            description="Play or queue a song for the user. Use this whenever someone asks to play, queue, add or listen to music. "
            "`query` is the song title and artist (e.g. 'Daft Punk - Get Lucky') or a YouTube URL. "
            "Joins the user's current voice channel and queues the track if something is already playing.",
        ),
        StructuredTool.from_function(
            coroutine=music_play_many,
            name="music_play_many",
            description="Queue several songs at once, in the background (returns immediately). Use this instead of repeated music_play calls when the user wants "
            f"more than one song (up to {_MAX_BATCH}). `queries` is a list of 'Artist - Title' strings or YouTube URLs. "
            "Joins the user's voice channel and starts playing if nothing is playing.",
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
            func=music_set_shuffle,
            name="music_set_shuffle",
            description="Turn shuffle mode on (enabled=true) or off (enabled=false). While on, the queue plays in random order.",
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
