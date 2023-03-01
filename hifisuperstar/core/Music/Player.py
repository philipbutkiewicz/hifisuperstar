# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
import validators
from hifisuperstar.core.Music.Media import media_get_source
from hifisuperstar.core.Music.Media import media_get_playlist
from hifisuperstar.io.Strings import str_hash_crc32
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import error
from hifisuperstar.core.Music.PlayCounter import PlayCounter
from hifisuperstar.core.Music.Playlist import Playlist
from discord.utils import get


class Player:
    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config
        self.options = {'volume': 0.02, 'repeat': False, 'repeat_all': False}

        self.play_counter = PlayCounter(self.ctx.guild.id)
        self.playlist = Playlist(self.ctx.guild.id)

        self.stopped = True
        self.prev = False
        self.jump_to_index = -1

    def get_play_counter(self):
        return self.play_counter

    def get_playlist(self):
        return self.playlist

    def after_track(self, arg):
        info(self, f"Track is over, args: {arg}", self.ctx.guild)

        if self.stopped:
            self.prev = False
            return False

        if self.playlist.is_over():
            info(self, 'Playlist is over', self.ctx.guild)
            self.prev = False
            return False

        if not self.options['repeat'] and self.jump_to_index == -1:
            if not self.prev:
                self.playlist.skip_track()

                if self.playlist.get_current_track_index() == -1:
                    if not self.options['repeat_all']:
                        self.stop_track()
                    else:
                        self.playlist.jump_to(0)
            else:
                self.playlist.prev_track()
        else:
            if self.jump_to_index > -1:
                self.playlist.jump_to(self.jump_to_index)
                self.jump_to_index = -1

        self.play_track()

    def play_track(self):
        info(self, 'Called')
        voice = get(self.ctx.bot.voice_clients, guild=self.ctx.guild)

        track = self.playlist.get_current_track()
        if track is None:
            error(self, 'No tracks in the playlist', self.ctx.guild)
            return False

        if voice.is_playing():
            voice.stop()

        try:
            info(self, f"Getting media source for track ID {track['id']}...", self.ctx.guild)
            (track_info, url, playback_url) = media_get_source(track['url'], allowed_mime_types=self.config['MusicCog']['Allowed_Mime_Types'])
        except:
            error(self, f"Could not get media source for track ID {track['id']}", self.ctx.guild)
            return False

        info(self, f"Increasing playback count for track ID {track['id']}...", self.ctx.guild)
        self.play_counter.count_playback(track)

        info(self, f"Beginning playback of track ID {track['id']}...", self.ctx.guild)
        voice.play(discord.FFmpegPCMAudio(playback_url, **{
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }), after=self.after_track)

        voice.source = discord.PCMVolumeTransformer(voice.source, volume=self.options['volume'])

        self.stopped = False

    def queue_track(self, query=None):
        voice = get(self.ctx.bot.voice_clients, guild=self.ctx.guild)

        track_info = None
        if query is not None:
            try:
                info(self, f"Getting media source for a track...", self.ctx.guild)
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

    async def queue_playlist(self, query):
        info(self, f"Attempting to queue a playlist: {query}...", self.ctx.guild)
        if validators.url(query):
            playlist_name = f"yt-{str_hash_crc32(query)}"

            info(self, f"Loading/creating playlist {playlist_name}", self.ctx.guild)
            playlist = Playlist(self.ctx.guild.id, playlist_name)
            if not playlist.load_from_storage():
                info(self, 'New playlist will be created', self.ctx.guild)
                entries = media_get_playlist(query)
                if not entries or len(entries) == 0:
                    error(self, 'Invalid link or playlist empty', self.ctx.guild)
                    return None

                for playlist_info in entries:
                    if playlist_info is not None:
                        playlist.add_track(playlist_info['title'], f"https://youtube.com/watch?v={playlist_info['id']}")

                playlist.save(cache=True)

            self.playlist = playlist
        else:
            info(self, f"A name was supplied, loading from storage for query: {query}...", self.ctx.guild)
            playlist = Playlist(self.ctx.guild.id, query)
            if not playlist.load_from_storage():
                error('Failed to load the playlist', self.ctx.guild)
                return None

            self.playlist = playlist

        return self.playlist.get_tracks()

    def skip_track(self):
        if self.stopped:
            return False

        self.jump_to_index = -1

        voice = get(self.ctx.bot.voice_clients, guild=self.ctx.guild)
        voice.stop()

    def skip_track_to_index(self, index):
        if self.stopped:
            return False

        self.jump_to_index = index
        self.prev = False

        voice = get(self.ctx.bot.voice_clients, guild=self.ctx.guild)
        voice.stop()

    def prev_track(self):
        if self.stopped:
            return False

        self.jump_to_index = -1
        self.prev = True

        voice = get(self.ctx.bot.voice_clients, guild=self.ctx.guild)
        voice.stop()

    async def stop_track(self):
        if self.stopped:
            return False

        voice = get(self.ctx.bot.voice_clients, guild=self.ctx.guild)
        if voice.is_playing():
            voice.stop()

        self.jump_to_index = -1
        self.prev = False
        self.stopped = True

        await voice.disconnect()

    def set_volume(self, volume):
        if self.stopped:
            return False

        voice = get(self.ctx.bot.voice_clients, guild=self.ctx.guild)

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
