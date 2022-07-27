# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2022 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import json
import os

from hifisuperstar.io.Logger import error, warn
from hifisuperstar.io.Strings import str_rand_crc32


class Playlist:

    def __init__(self, guild_id, name="Default"):
        self.guild_id = str(guild_id)
        self.name = name
        self.tracks = []

        self.current_index = 0

    def get_playlist_storage_path(self):
        playlist_storage_path = os.path.join('storage', 'playlists')
        if not os.path.exists(playlist_storage_path):
            os.mkdir(playlist_storage_path)

        guild_playlist_storage_path = os.path.join(playlist_storage_path, self.guild_id)
        if not os.path.exists(guild_playlist_storage_path):
            os.mkdir(guild_playlist_storage_path)

        return guild_playlist_storage_path

    def get_playlist_path(self):
        return os.path.join(self.get_playlist_storage_path(), f"{self.name}.json")

    def get_available_playlists(self):
        list_path = os.path.join(self.get_playlist_storage_path(), 'list.json')
        if os.path.exists(list_path):
            return json.loads(open(list_path, encoding='utf-8').read())

        return []

    def load_from_storage(self):
        playlist_path = self.get_playlist_path()

        if not os.path.exists(playlist_path):
            return False

        playlist = json.loads(open(playlist_path, encoding='utf-8').read())
        if not playlist:
            return False

        if 'name' not in playlist or 'guild_id' not in playlist or 'tracks' not in playlist:
            return False

        self.name = playlist['name']
        self.guild_id = playlist['guild_id']
        self.tracks = playlist['tracks']

        return True

    def save(self, cache=False):
        playlist_path = self.get_playlist_path()
        if os.path.exists(playlist_path):
            error(self, f"Failed saving the playlist to {playlist_path} because path already exists!")
            return False

        try:
            with open(playlist_path, 'w') as outfile:
                json.dump({
                    'name': self.name,
                    'guild_id': self.guild_id,
                    'tracks': self.tracks
                }, outfile)
        except:
            error(self, f"Failed saving the playlist to {playlist_path}")
            return False

        if not cache:
            available_playlists = self.get_available_playlists()
            if self.name not in available_playlists:
                available_playlists.append(self.name)

            if not self.save_available_playlists(available_playlists):
                return False

        return True

    def save_available_playlists(self, available_playlists):
        list_path = os.path.join(self.get_playlist_storage_path(), 'list.json')
        try:
            with open(list_path, 'w') as outfile:
                json.dump(available_playlists, outfile)
        except:
            error(self, f"Failed saving available playlists to {list_path}")
            return False

        return True

    def delete(self):
        if not self.load_from_storage():
            error(self, f"Failed deleting playlist {self.name} because it could not be loaded from storage")
            return False

        os.remove(self.get_playlist_path())

        available_playlists = self.get_available_playlists()
        available_playlists.remove(self.name)

        if not self.save_available_playlists(available_playlists):
            warn(self, f"Playlist {self.name} was only partially deleted!")

        return True

    def get_name(self):
        return self.name

    def set_name(self, name):
        self.name = name

    def add_track(self, title, url):
        tid = str_rand_crc32()
        self.tracks.append({
            'id': tid,
            'title': title,
            'url': url
        })

        return True

    def remove_track(self, tid):
        try:
            index = self.tracks.index(next(item for item in self.tracks if item['id'] == tid))
            self.tracks.pop(index)
        except:
            return False

        return True

    def is_over(self):
        return self.current_index == len(self.tracks)

    def get_tracks(self):
        return self.tracks

    def get_current_track(self):
        if len(self.tracks) == 0:
            return None

        return self.tracks[self.current_index]

    def get_current_track_index(self):
        return self.current_index

    def clear(self):
        self.current_index = 0
        self.tracks.clear()

    def skip_track(self):
        if len(self.tracks) == 0:
            return None

        if self.current_index < (len(self.tracks) - 1):
            self.current_index += 1
        else:
            self.current_index = -1

        return self.get_current_track()

    def prev_track(self):
        if len(self.tracks) == 0:
            return None

        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.tracks)

        return self.get_current_track()

    def jump_to(self, index):
        if len(self.tracks) == 0 or index < 0 or index > (len(self.tracks) - 1):
            return None

        self.current_index = index

        return self.get_current_track()
