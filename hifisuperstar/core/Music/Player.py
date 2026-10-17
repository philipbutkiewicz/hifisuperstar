#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import asyncio
import os
import random

import discord
import validators

from hifisuperstar.core.Music.Media import media_get_playlist, media_get_source
from hifisuperstar.core.Music.MediaErrors import describe_media_error
from hifisuperstar.core.Music.PlayCounter import PlayCounter
from hifisuperstar.core.Music.Playlist import Playlist
from hifisuperstar.core.Server.Server import connect_voice
from hifisuperstar.io.GuildConfig import get_guild_config
from hifisuperstar.io.Logger import error, info, warn
from hifisuperstar.io.Resources import load_resource, save_resource
from hifisuperstar.io.Strings import str_hash_crc32

DEFAULT_VOLUME = 0.02


class Player:
    def __init__(self, interaction, config):
        self.interaction = interaction
        self.config = config
        self.music_config = get_guild_config(config, "MusicCog", interaction.guild.id)
        self.options = {
            "volume": self._load_volume(),
            "repeat": False,
            "repeat_all": False,
            "shuffle": False,
        }

        self.play_counter = PlayCounter(self.interaction.guild.id)
        self.playlist = Playlist(self.interaction.guild.id)

        self.streaming = False
        self.stopped = True
        self.prev = False
        # Set by skip/prev so they override single-track repeat
        self._advance_requested = False
        self.jump_to_index = -1
        self._voice_task = None
        self._voice_channel = None
        self._recovering = False
        self._playback_id = 0
        self._stream_url = None
        self._restart_audio = False
        self._next_track_task = None
        # Incremented by stop_track so background batch queueing can notice a stop
        self.stop_count = 0
        # Human readable reason why the last queue_track/queue_playlist call failed
        self.last_error = None

    def _load_volume(self):
        """The volume last set in this guild, persisted so it survives restarts."""
        saved = load_resource("music", self.interaction.guild.id).get("volume")
        if isinstance(saved, (int, float)) and not isinstance(saved, bool):
            return min(1.0, max(0.0, float(saved)))
        return DEFAULT_VOLUME

    def _save_volume(self):
        guild_id = self.interaction.guild.id
        settings = load_resource("music", guild_id)
        settings["volume"] = self.options["volume"]
        try:
            save_resource("music", guild_id, settings)
        except OSError as exc:
            warn(self, f"Could not persist the volume: {exc}", self.interaction.guild)

    def get_play_counter(self):
        return self.play_counter

    def get_playlist(self):
        return self.playlist

    def after_track(self, arg):
        self.interaction.client.loop.call_soon_threadsafe(
            self._after_track, arg, self._playback_id
        )

    def _after_track(self, arg, playback_id):
        if playback_id != self._playback_id or self.stopped or self._recovering:
            return
        info(self, f"Track is over, args: {arg}", self.interaction.guild)
        if arg is not None:
            error(self, f"Audio playback failed: {arg}", self.interaction.guild)

        voice = self.interaction.guild.voice_client
        if voice is None or not voice.is_connected():
            self._restart_audio = True
            self._start_voice_monitor()
            return

        if self.streaming:
            self.stopped = True
            self.streaming = False
            return False

        # Consume the one-shot flags now, whatever happens below, so they never go stale
        go_back = self.prev
        manual = self._advance_requested
        self.prev = False
        self._advance_requested = False

        if self.jump_to_index > -1:
            if self.options["shuffle"]:
                self.playlist.remember_current()
            self.playlist.jump_to(self.jump_to_index)
            self.jump_to_index = -1
        elif self.options["repeat"] and not manual:
            pass  # replay the same track
        elif go_back:
            if self.options["shuffle"]:
                self.playlist.shuffle_prev()
            else:
                self.playlist.prev_track()
        elif not self._advance_playlist():
            asyncio.run_coroutine_threadsafe(
                self.stop_track(), self.interaction.client.loop
            )
            return False

        self._next_track_task = self.interaction.client.loop.create_task(
            self._resume_playback()
        )

    def _advance_playlist(self):
        """Moves to the next track; returns False when the queue is over."""
        if self.options["shuffle"]:
            self.playlist.shuffle_next()
        else:
            self.playlist.skip_track()

        if self.playlist.get_current_track_index() != -1:
            return True

        if not self.options["repeat_all"] or not self.playlist.get_tracks():
            return False

        if self.options["shuffle"]:
            # Everything played once: start a fresh random round
            self.playlist.reset_shuffle()
            self.playlist.current_index = random.randrange(
                len(self.playlist.get_tracks())
            )
        else:
            self.playlist.jump_to(0)
        return True

    async def _resume_playback(self, count=True):
        playback_id = self._playback_id
        stream_url = self._stream_url if self.streaming else None
        media_source = None
        if stream_url is None:
            failures = 0
            max_failures = max(1, len(self.playlist.get_tracks()))
            while True:
                track = self.playlist.get_current_track()
                if track is None:
                    self.stopped = True
                    return
                try:
                    media_source = await asyncio.to_thread(
                        media_get_source,
                        track["url"],
                        allowed_mime_types=self.music_config["Allowed_Mime_Types"],
                    )
                    break
                except Exception as exc:
                    error(
                        self,
                        f"Could not get media source for track ID {track['id']} - {exc}",
                        self.interaction.guild,
                    )
                    if playback_id != self._playback_id or self.stopped:
                        return
                    # One unplayable track (private, deleted, age-restricted) must not end the queue
                    failures += 1
                    if failures >= max_failures or not self._advance_playlist():
                        warn(
                            self,
                            "No playable tracks left in the queue",
                            self.interaction.guild,
                        )
                        await self.stop_track()
                        return
                    info(self, "Skipping the unplayable track", self.interaction.guild)
        if playback_id == self._playback_id and not self.stopped:
            self.play_track(stream_url, media_source=media_source, count=count)

    async def _resume_if_idle(self, voice):
        if voice.is_playing() or voice.is_paused():
            return
        if self._next_track_task is not None and not self._next_track_task.done():
            return
        # A restart after a dropped connection is not a new play of the track
        await self._resume_playback(count=False)

    def _start_voice_monitor(self):
        loop = self.interaction.client.loop
        try:
            on_loop = asyncio.get_running_loop() is loop
        except RuntimeError:
            on_loop = False
        if not on_loop:
            # create_task is not thread-safe, hop onto the bot's loop first
            loop.call_soon_threadsafe(self._start_voice_monitor)
            return
        if self._voice_task is None or self._voice_task.done():
            self._voice_task = loop.create_task(self._monitor_voice())

    async def _monitor_voice(self):
        try:
            while not self.stopped:
                await asyncio.sleep(2)
                voice = self.interaction.guild.voice_client
                if voice is not None and voice.is_connected():
                    self._voice_channel = voice.channel
                    if self._restart_audio:
                        self._restart_audio = False
                        await self._resume_if_idle(voice)
                    continue

                self._recovering = True
                recovery_id = self._playback_id
                info(
                    self,
                    "Voice connection lost; waiting for reconnect",
                    self.interaction.guild,
                )
                # Give discord.py's own voice reconnect loop time to resume the existing audio.
                for _ in range(5):
                    await asyncio.sleep(2)
                    if recovery_id != self._playback_id:
                        break
                    voice = self.interaction.guild.voice_client
                    if voice is not None and voice.is_connected():
                        break
                else:
                    self._playback_id += 1
                    recovery_id = self._playback_id
                    next_track = self._next_track_task
                    if next_track is not None and not next_track.done():
                        next_track.cancel()
                        try:
                            await next_track
                        except asyncio.CancelledError:
                            pass
                    for attempt in range(3):
                        if recovery_id != self._playback_id:
                            break
                        try:
                            voice = await connect_voice(self._voice_channel)
                            if not voice.is_connected():
                                raise discord.ClientException(
                                    "Voice connection did not complete"
                                )
                            break
                        except (TimeoutError, discord.DiscordException, OSError) as exc:
                            error(
                                self,
                                f"Voice reconnect attempt {attempt + 1} failed: {exc}",
                                self.interaction.guild,
                            )
                            if attempt == 2:
                                await self.stop_track()
                                return
                            await asyncio.sleep(5 * (attempt + 1))

                self._recovering = False
                self._restart_audio = False
                voice = self.interaction.guild.voice_client
                if voice is not None and voice.is_connected():
                    await self._resume_if_idle(voice)
        finally:
            self._recovering = False

    def play_track(self, stream_url=None, *, media_source=None, count=True):
        info(self, "Called")
        voice = self.interaction.guild.voice_client

        if voice is None or not voice.is_connected():
            error(
                self,
                "Cannot play while disconnected from voice",
                self.interaction.guild,
            )
            if not self.stopped:
                self._restart_audio = True
                self._start_voice_monitor()
            return False

        self._playback_id += 1
        self._restart_audio = False
        # A new playback makes any pending skip/prev request obsolete
        self.prev = False
        self._advance_requested = False
        playback_id = self._playback_id
        self.streaming = stream_url is not None
        self._stream_url = stream_url
        self._voice_channel = voice.channel

        playback_url = None
        track = None
        if stream_url is None:
            track = self.playlist.get_current_track()
            if track is None:
                error(self, "No tracks in the playlist", self.interaction.guild)
                self.stopped = True
                return False

            if voice.is_playing():
                voice.stop()

            try:
                info(
                    self,
                    f"Getting media source for track ID {track['id']}...",
                    self.interaction.guild,
                )
                if media_source is None:
                    media_source = media_get_source(
                        track["url"],
                        allowed_mime_types=self.music_config["Allowed_Mime_Types"],
                    )
                (_track_info, _url, playback_url) = media_source
            except Exception as e:
                error(
                    self,
                    f"Could not get media source for track ID {track['id']} - {e!s}",
                    self.interaction.guild,
                )
                self.stopped = True
                return False

            if count:
                info(
                    self,
                    f"Increasing playback count for track ID {track['id']}...",
                    self.interaction.guild,
                )
                self.play_counter.count_playback(track)
        else:
            self.streaming = True
            playback_url = stream_url

        info(
            self,
            f"Beginning playback of {track['id'] if track is not None else 'radio'}...",
            self.interaction.guild,
        )
        # -reconnect flags are HTTP-only; ffmpeg rejects them outright when playing a local cached file
        is_local_file = os.path.exists(playback_url) if playback_url else False
        ffmpeg_options = {"options": "-vn"}
        if not is_local_file:
            ffmpeg_options["before_options"] = (
                "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
            )

        try:
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(playback_url, **ffmpeg_options),
                volume=self.options["volume"],
            )
        except (discord.ClientException, OSError) as exc:
            error(self, f"Could not create audio source: {exc}", self.interaction.guild)
            self.stopped = True
            return False
        try:
            voice.play(
                source,
                after=lambda exc: self.interaction.client.loop.call_soon_threadsafe(
                    self._after_track, exc, playback_id
                ),
            )
        except discord.ClientException as exc:
            source.cleanup()
            error(
                self, f"Could not start audio playback: {exc}", self.interaction.guild
            )
            if voice.is_connected():
                self.stopped = True
                return False
            self.stopped = False
            self._restart_audio = True
            self._start_voice_monitor()
            return False

        self.stopped = False
        self._start_voice_monitor()
        asyncio.run_coroutine_threadsafe(
            self.interaction.client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name=track["title"] if track is not None else None,
                    title=track["title"] if track is not None else None,
                )
            ),
            self.interaction.client.loop,
        )
        return True

    async def queue_track(self, query=None):
        voice = self.interaction.guild.voice_client
        if voice is None or not voice.is_connected():
            error(
                self,
                "Cannot queue playback while disconnected from voice",
                self.interaction.guild,
            )
            return False

        self.last_error = None
        allowed_mime_types = self.music_config["Allowed_Mime_Types"]
        media_source = None
        track_info = None
        if query is not None:
            try:
                info(
                    self, "Getting media source for a track...", self.interaction.guild
                )
                media_source = await asyncio.to_thread(
                    media_get_source, query, allowed_mime_types=allowed_mime_types
                )
            except Exception as exc:
                error(
                    self, f"Could not get media source - {exc}", self.interaction.guild
                )
                self.last_error = describe_media_error(exc)
                return False

            (source_info, url, _playback_url) = media_source
            title = (source_info.get("info") or {}).get("title") or url
            track_info = source_info.get("info") or {"title": title}
            self.playlist.add_track(title, url)
        elif len(self.playlist.get_tracks()) == 0:
            self.last_error = "the queue is empty."
            return False

        if self.streaming:
            # Switching from the radio to a track: stop the stream without triggering the end-of-track handler
            self._playback_id += 1
            self.streaming = False
            self._stream_url = None
            if voice.is_playing():
                voice.stop()

        if not voice.is_playing() and not voice.is_paused():
            current = self.playlist.get_current_track()
            if current is None:
                return False
            if media_source is None or media_source[1] != current["url"]:
                try:
                    media_source = await asyncio.to_thread(
                        media_get_source,
                        current["url"],
                        allowed_mime_types=allowed_mime_types,
                    )
                except Exception as exc:
                    error(
                        self,
                        f"Could not get media source for track ID {current['id']} - {exc}",
                        self.interaction.guild,
                    )
                    self.last_error = describe_media_error(exc)
                    return False
            if self.play_track(media_source=media_source) is False:
                self.last_error = "playback could not be started (see the bot log for details)."
                return False

        return track_info if query is not None else True

    def queue_radio(self):
        voice = self.interaction.guild.voice_client
        if voice is None or not voice.is_connected():
            error(
                self,
                "Cannot play radio while disconnected from voice",
                self.interaction.guild,
            )
            return False

        return (
            voice.is_playing()
            or self.play_track(self.music_config["Radio_URL"]) is not False
        )

    async def queue_playlist(self, query, reimport=False):
        self.last_error = None
        info(
            self, f"Attempting to queue a playlist: {query}...", self.interaction.guild
        )
        if validators.url(query):
            playlist_name = f"yt-{str_hash_crc32(query)}"

            info(
                self,
                f"Loading/creating playlist {playlist_name}",
                self.interaction.guild,
            )
            playlist = Playlist(self.interaction.guild.id, playlist_name)
            if reimport or not playlist.load_from_storage():
                info(
                    self,
                    "Playlist will be re-imported"
                    if reimport
                    else "New playlist will be created",
                    self.interaction.guild,
                )
                errors = []
                entries = await asyncio.to_thread(media_get_playlist, query, errors)
                if not entries or len(entries) == 0:
                    error(
                        self, "Invalid link or playlist empty", self.interaction.guild
                    )
                    self.last_error = (
                        errors[0]
                        if errors
                        else "the playlist is empty, private or unavailable."
                    )
                    return None

                for playlist_info in entries:
                    if playlist_info is not None:
                        playlist.add_track(
                            playlist_info.get("title") or playlist_info["id"],
                            f"https://youtube.com/watch?v={playlist_info['id']}",
                        )

                # A failed fetch returns above, so the existing cached copy is only replaced by a good one
                playlist.save(cache=True, overwrite=True)

            self.playlist = playlist
        else:
            info(
                self,
                f"A name was supplied, loading from storage for query: {query}...",
                self.interaction.guild,
            )
            playlist = Playlist(self.interaction.guild.id, query)
            if not playlist.load_from_storage():
                error(self, "Failed to load the playlist", self.interaction.guild)
                self.last_error = f"there is no saved playlist named '{query}'."
                return None

            self.playlist = playlist

        return self.playlist.get_tracks()

    def skip_track(self):
        if self.stopped or self.streaming:
            return False

        self.jump_to_index = -1
        self.prev = False
        self._advance_requested = True

        voice = self.interaction.guild.voice_client
        if voice is None or not voice.is_connected():
            error(
                self,
                "Cannot skip while disconnected from voice",
                self.interaction.guild,
            )
            return False
        voice.stop()
        return True

    def skip_track_to_index(self, index):
        if self.stopped or self.streaming:
            return False

        self.jump_to_index = index
        self.prev = False

        voice = self.interaction.guild.voice_client
        if voice is None or not voice.is_connected():
            error(
                self,
                "Cannot jump while disconnected from voice",
                self.interaction.guild,
            )
            return False
        voice.stop()
        return True

    def prev_track(self):
        if self.stopped or self.streaming:
            return False

        self.jump_to_index = -1
        self.prev = True
        self._advance_requested = True

        voice = self.interaction.guild.voice_client
        if voice is None or not voice.is_connected():
            error(
                self,
                "Cannot go back while disconnected from voice",
                self.interaction.guild,
            )
            return False
        voice.stop()
        return True

    async def stop_track(self):
        self.stop_count += 1
        self._playback_id += 1
        self.jump_to_index = -1
        self.prev = False
        self._advance_requested = False
        self.stopped = True
        self.streaming = False
        self._stream_url = None
        self._restart_audio = False
        next_track = self._next_track_task
        if next_track is not None and next_track is not asyncio.current_task():
            next_track.cancel()
            try:
                await next_track
            except asyncio.CancelledError:
                pass
        self._next_track_task = None
        task = self._voice_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._voice_task = None
        self._recovering = False

        voice = self.interaction.guild.voice_client
        if voice is not None:
            voice.stop()
            try:
                await voice.disconnect(force=True)
            except (TimeoutError, discord.DiscordException, OSError) as exc:
                error(self, f"Voice disconnect failed: {exc}", self.interaction.guild)

        await self.interaction.client.change_presence(activity=None)

    def set_volume(self, volume):
        self.options["volume"] = min(1.0, max(0.0, float(volume)))
        self._save_volume()

        # Applies to the track that is playing right now, later tracks pick the value up in play_track
        voice = self.interaction.guild.voice_client
        if voice is not None and voice.source:
            voice.source.volume = self.options["volume"]

        return True

    def mode_reminder(self):
        """A short note about the playback modes that are on (empty when none), so users don't think the bot is broken."""
        notes = []
        if self.options["repeat"]:
            notes.append(
                "🔂 Repeat is on: the same track keeps replaying until you turn it off with /repeat."
            )
        if self.options["repeat_all"]:
            notes.append(
                "🔁 Repeat all is on: the queue starts over when it ends (turn it off with /repeat_all)."
            )
        if self.options["shuffle"]:
            notes.append(
                "🔀 Shuffle is on: tracks play in random order (turn it off with /shuffle)."
            )
        return "\n".join(f"-# {note}" for note in notes)

    def set_repeat(self):
        self.options["repeat"] = not self.options["repeat"]
        return self.options["repeat"]

    def set_shuffle(self, enabled=None):
        """Toggles shuffle (or sets it explicitly) and returns the new state."""
        self.options["shuffle"] = (
            not self.options["shuffle"] if enabled is None else bool(enabled)
        )
        # Start a fresh round; whatever is playing right now counts as played
        self.playlist.reset_shuffle()
        if self.options["shuffle"]:
            current = self.playlist.get_current_track()
            if current is not None:
                self.playlist.shuffle_played.add(current["id"])
        return self.options["shuffle"]

    def set_repeat_all(self):
        self.options["repeat_all"] = not self.options["repeat_all"]
        return self.options["repeat_all"]
