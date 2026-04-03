import os
from zipfile import ZipFile
from argparse import ArgumentParser
from hifisuperstar.core.Music.Media import media_get_source

from hifisuperstar.core.Music.Playlist import Playlist
from hifisuperstar.io.Strings import str_hash_sha256

def pack_playlist(playlist_name, guild_id, output):
    playlist = Playlist(guild_id, playlist_name)
    if not playlist.load_from_storage():
        print('Playlist does not exist or is broken\n')
        exit(1)

    outfile = output if output is not None else f'{playlist_name}.zip'
    with ZipFile(outfile, 'w') as zipfile:
        track_index = 1
        for track in playlist.tracks:
            (track_info, url, playback_url) = media_get_source(track['url'])
            track_path = f"cache/{str_hash_sha256(url)}.m4a"
            if not os.path.exists(track_path):
                print(f"!! Track '{track['title']}' not found in path '{track_path}' - derived from query '{url}'!")
            else:
                print(f"Storing '{track['title']}'...")
                zipfile.write(track_path, f"{str(track_index).rjust(3, '0')}. {track['title']}.m4a")
                track_index += 1
    
    print('Done!')

argparser = ArgumentParser()
argparser.add_argument('-p', '--playlist', help='Playlist to pack', type=str)
argparser.add_argument('-g', '--guild', help='Guild ID', type=int)
argparser.add_argument('-o', '--output', help='Output file name', type=str)
args = argparser.parse_args()

if args.playlist and args.guild:
    pack_playlist(args.playlist, args.guild, args.output)