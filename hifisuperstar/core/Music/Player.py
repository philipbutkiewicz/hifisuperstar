#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import asyncio
import os

import discord
import validators

from hifisuperstar.core.Music.Media import media_get_playlist, media_get_source
from hifisuperstar.core.Music.PlayCounter import PlayCounter
from hifisuperstar.core.Music.Playlist import Playlist
from hifisuperstar.core.Server.Server import connect_voice
from hifisuperstar.io.GuildConfig import get_guild_config
from hifisuperstar.io.Logger import error, info
from hifisuperstar.io.Strings import str_hash_crc32


class Player:
    def __init__(self, interaction, config):
        self.interaction = interaction
        self.config = config
        self.music_config = get_guild_config(config, "MusicCog", interaction.guild.id)
        self.options = {"volume": 0.02, "repeat": False, "repeat_all": False}

        self.play_counter = PlayCounter(self.interaction.guild.id)
        self.playlist = Playlist(self.interaction.guild.id)

        self.streaming = False
        self.stopped = True
        self.prev = False
        self.jump_to_index = -1
        self._voice_task = None
        self._voice_channel = None
        self._recovering = False
        self._playback_id = 0
        self._stream_url = None
        self._restart_audio = False
        self._next_track_task = None

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

        if not self.options["repeat"] and self.jump_to_index == -1:
            if not self.prev:
                self.playlist.skip_track()

                if self.playlist.get_current_track_index() == -1:
                    if not self.options["repeat_all"]:
                        asyncio.run_coroutine_threadsafe(
                            self.stop_track(), self.interaction.client.loop
                        )
                        return False
                    else:
                        self.playlist.jump_to(0)
            else:
                self.playlist.prev_track()
                self.prev = False
        else:
            if self.jump_to_index > -1:
                self.playlist.jump_to(self.jump_to_index)
                self.jump_to_index = -1

        self._next_track_task = self.interaction.client.loop.create_task(
            self._resume_playback()
        )

    async def _resume_playback(self):
        playback_id = self._playback_id
        stream_url = self._stream_url if self.streaming else None
        media_source = None
        if stream_url is None:
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
            except Exception as exc:
                error(
                    self,
                    f"Could not get media source for track ID {track['id']} - {exc}",
                    self.interaction.guild,
                )
                if playback_id == self._playback_id:
                    self.stopped = True
                return
        if playback_id == self._playback_id and not self.stopped:
            self.play_track(stream_url, media_source=media_source)

    async def _resume_if_idle(self, voice):
        if voice.is_playing() or voice.is_paused():
            return
        if self._next_track_task is not None and not self._next_track_task.done():
            return
        await self._resume_playback()

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

    def play_track(self, stream_url=None, *, media_source=None):
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
                return False

            (source_info, url, _playback_url) = media_source
            title = (source_info.get("info") or {}).get("title") or url
            track_info = source_info.get("info") or {"title": title}
            self.playlist.add_track(title, url)
        elif len(self.playlist.get_tracks()) == 0:
            return False

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
                    return False
            if self.play_track(media_source=media_source) is False:
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

    async def queue_playlist(self, query):
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
            if not playlist.load_from_storage():
                info(self, "New playlist will be created", self.interaction.guild)
                entries = await asyncio.to_thread(media_get_playlist, query)
                if not entries or len(entries) == 0:
                    error(
                        self, "Invalid link or playlist empty", self.interaction.guild
                    )
                    return None

                for playlist_info in entries:
                    if playlist_info is not None:
                        playlist.add_track(
                            playlist_info["title"],
                            f"https://youtube.com/watch?v={playlist_info['id']}",
                        )

                playlist.save(cache=True)

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
                return None

            self.playlist = playlist

        return self.playlist.get_tracks()

    def skip_track(self):
        if self.stopped or self.streaming:
            return False

        self.jump_to_index = -1
        self.prev = False

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
        self._playback_id += 1
        self.jump_to_index = -1
        self.prev = False
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
        if self.stopped:
            return False

        voice = self.interaction.guild.voice_client

        self.options["volume"] = float(volume)
        if voice is not None and voice.source:
            voice.source.volume = self.options["volume"]
        else:
            return False

        return True

    def set_repeat(self):
        self.options["repeat"] = not self.options["repeat"]
        return self.options["repeat"]

    def set_repeat_all(self):
        self.options["repeat_all"] = not self.options["repeat_all"]
        return self.options["repeat_all"]
