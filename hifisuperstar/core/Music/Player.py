# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import asyncio
import discord
import validators
from hifisuperstar.core.Music.Media import media_get_source
from hifisuperstar.core.Music.Media import media_get_playlist
from hifisuperstar.io.Strings import str_hash_crc32, str_rand_crc32
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import error
from hifisuperstar.core.Music.PlayCounter import PlayCounter
from hifisuperstar.core.Music.Playlist import Playlist


class Player:
    def __init__(self, interaction, config):
        self.interaction = interaction
        self.config = config
        self.options = {'volume': 0.02, 'repeat': False, 'repeat_all': False}

        self.play_counter = PlayCounter(self.interaction.guild.id)
        self.playlist = Playlist(self.interaction.guild.id)

        self.streaming = False
        self.stopped = True
        self.prev = False
        self.jump_to_index = -1

    def get_play_counter(self):
        return self.play_counter

    def get_playlist(self):
        return self.playlist

    def after_track(self, arg):
        info(self, f"Track is over, args: {arg}", self.interaction.guild)

        if self.streaming:
            return False

        if self.stopped:
            self.prev = False
            return False

        if self.playlist.is_over():
            info(self, 'Playlist is over', self.interaction.guild)
            self.prev = False
            asyncio.run_coroutine_threadsafe(
                self.interaction.client.change_presence(activity=None),
                self.interaction.client.loop
            )
            return False

        if not self.options['repeat'] and self.jump_to_index == -1:
            if not self.prev:
                self.playlist.skip_track()

                if self.playlist.get_current_track_index() == -1:
                    if not self.options['repeat_all']:
                        import asyncio
                        asyncio.run_coroutine_threadsafe(self.stop_track(), self.interaction.client.loop)
                    else:
                        self.playlist.jump_to(0)
            else:
                self.playlist.prev_track()
        else:
            if self.jump_to_index > -1:
                self.playlist.jump_to(self.jump_to_index)
                self.jump_to_index = -1

        self.play_track()

    def play_track(self, stream_url=None):
        info(self, 'Called')
        voice = self.interaction.guild.voice_client

        if self.streaming:
            self.stop_track()

        playback_url = None
        track = None
        if stream_url is None:
            track = self.playlist.get_current_track()
            if track is None:
                error(self, 'No tracks in the playlist', self.interaction.guild)
                return False

            if voice.is_playing():
                voice.stop()

            try:
                info(self, f"Getting media source for track ID {track['id']}...", self.interaction.guild)
                (track_info, url, playback_url) = media_get_source(track['url'], allowed_mime_types=self.config['MusicCog']['Allowed_Mime_Types'])
            except Exception as e:
                error(self, f"Could not get media source for track ID {track['id']} - {str(e)}", self.interaction.guild)
                return False

            info(self, f"Increasing playback count for track ID {track['id']}...", self.interaction.guild)
            self.play_counter.count_playback(track)
        else:
            self.streaming = True
            playback_url = stream_url

        info(self, f"Beginning playback of {track['id'] if track is not None else 'radio'}...", self.interaction.guild)
        voice.play(discord.FFmpegPCMAudio(playback_url, **{
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }), after=self.after_track)

        voice.source = discord.PCMVolumeTransformer(voice.source, volume=self.options['volume'])

        self.stopped = False
        asyncio.run_coroutine_threadsafe(
            self.interaction.client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name=track['title'] if track is not None else None,
                    title=track['title'] if track is not None else None
                )
            ),
            self.interaction.client.loop
        )

    def queue_track(self, query=None):
        voice = self.interaction.guild.voice_client

        track_info = None
        if query is not None:
            try:
                info(self, f"Getting media source for a track...", self.interaction.guild)
                (track_info, url, playback_url) = media_get_source(query, allowed_mime_types=self.config['MusicCog']['Allowed_Mime_Types'])
            except:
                return False

            self.playlist.add_track(track_info['info']['title'], query)
        else:
            if len(self.playlist.get_tracks()) == 0:
                return False

        if not voice.is_playing():
            self.play_track()

        return track_info['info'] if query is not None else True    
    
    def queue_radio(self):
        voice = self.interaction.guild.voice_client

        if not voice.is_playing():
            self.play_track(self.config['MusicCog']['Radio_URL'])

        return True

    async def queue_playlist(self, query):
        info(self, f"Attempting to queue a playlist: {query}...", self.interaction.guild)
        if validators.url(query):
            playlist_name = f"yt-{str_hash_crc32(query)}"

            info(self, f"Loading/creating playlist {playlist_name}", self.interaction.guild)
            playlist = Playlist(self.interaction.guild.id, playlist_name)
            if not playlist.load_from_storage():
                info(self, 'New playlist will be created', self.interaction.guild)
                entries = media_get_playlist(query)
                if not entries or len(entries) == 0:
                    error(self, 'Invalid link or playlist empty', self.interaction.guild)
                    return None

                for playlist_info in entries:
                    if playlist_info is not None:
                        playlist.add_track(playlist_info['title'], f"https://youtube.com/watch?v={playlist_info['id']}")

                playlist.save(cache=True)

            self.playlist = playlist
        else:
            info(self, f"A name was supplied, loading from storage for query: {query}...", self.interaction.guild)
            playlist = Playlist(self.interaction.guild.id, query)
            if not playlist.load_from_storage():
                error(self, 'Failed to load the playlist', self.interaction.guild)
                return None

            self.playlist = playlist

        return self.playlist.get_tracks()

    def skip_track(self):
        if self.stopped or self.streaming:
            return False

        self.jump_to_index = -1

        voice = self.interaction.guild.voice_client
        voice.stop()

    def skip_track_to_index(self, index):
        if self.stopped or self.streaming:
            return False

        self.jump_to_index = index
        self.prev = False

        voice = self.interaction.guild.voice_client
        voice.stop()

    def prev_track(self):
        if self.stopped or self.streaming:
            return False

        self.jump_to_index = -1
        self.prev = True

        voice = self.interaction.guild.voice_client
        voice.stop()

    async def stop_track(self):
        if self.stopped:
            return False

        voice = self.interaction.guild.voice_client
        if voice.is_playing():
            voice.stop()

        self.jump_to_index = -1
        self.prev = False
        self.stopped = True
        self.streaming = False

        await self.interaction.client.change_presence(activity=None)
        await voice.disconnect()

    def set_volume(self, volume):
        if self.stopped:
            return False

        voice = self.interaction.guild.voice_client

        self.options['volume'] = float(volume)
        if voice.source:
            voice.source.volume = self.options['volume']
        else:
            return False

        return True

    def set_repeat(self):
        self.options['repeat'] = not self.options['repeat']
        return self.options['repeat']

    def set_repeat_all(self):
        self.options['repeat_all'] = not self.options['repeat_all']
        return self.options['repeat_all']
