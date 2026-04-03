# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import json
import hashlib
import os
import re

from flask import render_template, current_app


class PlaylistController:

    def list(self, guild_id):
        if not re.match('^[0-9]+$', guild_id):
            return render_template('error.html', error='Invalid guild ID.', code=400), 400
        if not os.path.exists(self.get_playlist_storage_path(guild_id)):
            return render_template('error.html', error='This guild has no playlists.', code=404)

        list_path = os.path.join(self.get_playlist_storage_path(guild_id), 'list.json')
        if not os.path.exists(list_path):
            return render_template('error.html', error='This guild has no playlists.', code=404)

        with open(list_path) as listfile:
            playlists = json.loads(listfile.read())

        return render_template('playlists/list.html', playlists=playlists, guild_id=guild_id)

    def show(self, guild_id, name):
        if not re.match('^[0-9]+$', guild_id):
            return render_template('error.html', error='Invalid guild ID.', code=400), 400
        if not re.match('^[a-zA-Z0-9\~\`\!\@\#\$\%\^\&\*\(\)\-\_\=\+\[\]\{\}\|\;\'\:\"\,\.\/\<\>\?\ ]+$', name):
            return render_template('error.html', error='Invalid playlist name.', code=400), 400

        playlist = self.load_playlist(name, guild_id)
        if playlist is None:
            return render_template('error.html', error='Could not find a playlist with that name.', code=404), 404

        return render_template('playlists/show.html', playlist=playlist)

    def load_playlist(self, name, guild_id):
        playlist_path = self.get_playlist_path(name, guild_id)

        if not os.path.exists(playlist_path):
            return None

        playlist = json.loads(open(playlist_path, encoding='utf-8').read())
        if not playlist:
            return None

        if 'name' not in playlist or 'guild_id' not in playlist or 'tracks' not in playlist:
            return None

        return playlist
    
    def str_hash_sha256(self, string):
        return hashlib.sha256(string.encode('utf-8')).hexdigest()

    @staticmethod
    def get_playlist_storage_path(guild_id):
        playlist_storage_path = os.path.join(os.path.join(current_app.config['BASE_APP_PATH'], 'storage'), 'playlists')
        if not os.path.exists(playlist_storage_path):
            os.mkdir(playlist_storage_path)

        guild_playlist_storage_path = os.path.join(playlist_storage_path, guild_id)
        if not os.path.exists(guild_playlist_storage_path):
            os.mkdir(guild_playlist_storage_path)

        return guild_playlist_storage_path

    def get_playlist_path(self, name, guild_id):
        return os.path.join(self.get_playlist_storage_path(guild_id), f"{self.str_hash_sha256(name)}.json")
