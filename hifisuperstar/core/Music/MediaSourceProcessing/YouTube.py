# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import threading
import os
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import error
from hifisuperstar.io.Logger import warn
from hifisuperstar.io.Strings import str_hash_sha256
from yt_dlp import YoutubeDL


def media_get_youtube_direct(url):
    info(None, f"YouTube: Extracting YouTube link info for query '{url}'...")
    with YoutubeDL(get_ydl_opts()) as ydl:
        yt_info = ydl.extract_info(url, download=False)

        track_info = {
            'info': yt_info,
            'is_youtube': True
        }

        download_youtube_media(url)

        return track_info, url, get_best_audio_url(yt_info)


def media_get_youtube_query(query):
    info(None, f"YouTube: Performing a YouTube search for query '{query}'...")
    with YoutubeDL(get_ydl_opts()) as ydl:
        yt_info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]

        track_info = {
            'info': yt_info,
            'is_youtube': True
        }

        url = f"https://youtube.com/watch?v={yt_info['id']}"

        download_youtube_media(url)

        return track_info, url, get_best_audio_url(yt_info)

def media_get_youtube_playlist(url):
    try:
        ydl_opts = get_ydl_opts()
        ydl_opts['noplaylist'] = False
        ydl_opts['download'] = False
        ydl_opts['ignoreerrors'] = True

        with YoutubeDL(ydl_opts) as ydl:
            yt_info = ydl.extract_info(url, False)
            return yt_info['entries']
    except:
        return None


def download_youtube_media(url):
    info(None, f"YouTube: Starting cache download thread for '{url}'...")
    thread = threading.Thread(target=download_youtube_media_thread, args=(url,))
    thread.start()


def download_youtube_media_thread(url):
    with YoutubeDL(get_ydl_opts(url)) as ydl:
        try:
            ydl.download([url])
        except:
            error(None, f"YouTube: Cache download failed for '{url}'. Download will be resumed the next time this track is played")


def get_best_audio_url(yt_info):
    best_format = None
    for format in yt_info['formats']:
        if format['resolution'] == 'audio only' and format['ext'] == 'm4a' and (best_format == None or best_format['quality'] < format['quality']):
            best_format = format
        
    return None if best_format is None else best_format['url']

def get_ydl_opts(query=None):
    cache_tpl = f"cache/{str_hash_sha256(query)}" if query is not None else ''
    if os.path.exists(os.path.join('normalized', cache_tpl)):
        cache_tpl = os.path.join('normalized', cache_tpl)
        warn(self, f'Normalized file in "{cache_tpl}" does exists')
    else:
        warn(self, f'Normalized file in "{cache_tpl}" does not exist!')
    return {
        'format': 'm4a/bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a'
        }],
        'noplaylist': True,
        'outtmpl': cache_tpl
    }