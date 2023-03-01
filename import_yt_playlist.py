#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

from argparse import ArgumentParser

from hifisuperstar.core.Music.Media import media_get_playlist
from hifisuperstar.core.Music.Playlist import Playlist

argparser = ArgumentParser()
argparser.add_argument('-u', '--url', help='Playlist URL', type=str)
argparser.add_argument('-gid', '--guild_id', help='Guild ID', type=str)
argparser.add_argument('-n', '--name', help='Playlist name', type=str)
args = argparser.parse_args()

entries = media_get_playlist(args.url)
if not entries or len(entries) == 0:
    print('Imported playlist was empty.')

playlist = Playlist(args.guild_id, args.name)
for playlist_info in entries:
    if playlist_info is not None:
        playlist.add_track(playlist_info['title'], f"https://youtube.com/watch?v={playlist_info['id']}")

playlist.save()
