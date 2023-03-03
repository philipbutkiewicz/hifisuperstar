#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import validators
import spotipy
from hifisuperstar.core.Music.Playlist import Playlist
from hifisuperstar.io.Logger import info, error
from urllib.parse import urlparse
from spotipy.oauth2 import SpotifyClientCredentials


class Client:
    def __init__(self, config):
        self.config = config


    def get_playlist(self, ctx, birdy_uri):
        if not self.get_birdy_uri_type(birdy_uri) == 'playlist':
            error(self, f"Spotify: Given birdy URI '{birdy_uri}' is not a playlist!")
            return None
        
        playlist_id = self.get_birdy_uri_param(birdy_uri)
        if playlist_id is None:
            error(self, f"Spotify: Given birdy URI '{birdy_uri}' does not contain a playlist ID!")
            return None
        
        try:
            spotify = self.get_spotify_client()
            
            spotify_playlist = spotify.playlist(playlist_id)
            if not spotify_playlist:
                error(self, f"Spotify: Unable to fetch playlist information for Spotify playlist ID '{playlist_id}'!")
                return None

            playlist = Playlist(ctx.guild.id)
            playlist.set_name(spotify_playlist['name'])

            for spotify_track in spotify_playlist['tracks']['items']:
                track_str = f"{', '.join(spotify_artist['name'] for spotify_artist in spotify_track['track']['artists'])} - {spotify_track['track']['name']}"
                playlist.add_track(track_str, track_str)

            return playlist

        except Exception as e:
            error(self, f"Spotify: Exception occurred - {str(e)}")
            return None


    def get_birdy_uri(self, spotify_url):
        if not validators.url(spotify_url):
            error(self, 'Spotify: Invalid URL!')
            return False

        parsed_url = urlparse(spotify_url.replace('www.', ''))
        if not parsed_url.netloc == 'open.spotify.com':
            error(self, 'Spotify: Invalid domain!')
            return False
        
        parsed_path = parsed_url.path[1:len(parsed_url.path)].split('/') if len(parsed_url) > 0 else []
        
        if len(parsed_path) < 2:
            error(self, 'Spotify: Invalid Spotify URL, missing type/id params.')
            return False
        
        return f"spotify:{parsed_path[0]}:{parsed_path[1]}"
    

    def get_birdy_uri_type(self, birdy_uri):
        birdy_uri_parts = self.get_birdy_uri_parts(birdy_uri)

        return birdy_uri_parts[1] if birdy_uri_parts is not None else None
    

    def get_birdy_uri_param(self, birdy_uri):
        birdy_uri_parts = self.get_birdy_uri_parts(birdy_uri)

        return birdy_uri_parts[2] if birdy_uri_parts is not None else None
    

    def get_birdy_uri_parts(self, birdy_uri):
        birdy_uri_split = birdy_uri.split(':')

        if len(birdy_uri_split) < 3:
            error(self, f"Invalid birdy URI: '{birdy_uri}'")

        return birdy_uri_split if len(birdy_uri_split) == 3 else None

        
    def get_spotify_client(self):
        if not 'SpotifyCog' in self.config or not 'Client_ID' in self.config['SpotifyCog'] or not 'Client_Secret' in self.config['SpotifyCog']:
            error(self, 'Spotify: Missing Spotify client ID/secret!')
            return None
        
        return spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(self.config['SpotifyCog']['Client_ID'], self.config['SpotifyCog']['Client_Secret']))
