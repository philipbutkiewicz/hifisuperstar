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

        return track_info, url, get_cached_track_path(url) or get_best_audio_url(yt_info)


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

        return track_info, url, get_cached_track_path(url) or get_best_audio_url(yt_info)

def media_get_youtube_playlist(url):
    # A single extract_info call can silently stop following continuation pages partway through very
    # large playlists (no error, just fewer entries), so fetch it in explicit playliststart/playlistend
    # ranges instead, forcing a separate request per page until a short/empty page signals the end.
    page_size = 100
    start = 1
    entries = []

    try:
        while True:
            ydl_opts = {
                'quiet': True,
                'ignoreerrors': 'only_download',
                'extract_flat': 'in_playlist',
                'noplaylist': False,
                'playliststart': start,
                'playlistend': start + page_size - 1,
                'extractor_retries': 10,
                'socket_timeout': 30
            }

            with YoutubeDL(ydl_opts) as ydl:
                yt_info = ydl.extract_info(url, download=False)

            page_entries = (yt_info or {}).get('entries') or []
            entries.extend(page_entries)

            if len(page_entries) < page_size:
                break

            start += page_size

        return entries
    except Exception as e:
        error(None, f"YouTube: Failed to fetch playlist '{url}' - {str(e)}")
        return None


def media_search_youtube(query, limit=25):
    info(None, f"YouTube: Searching for '{query}' (limit {limit})...")
    with YoutubeDL({'quiet': True, 'extract_flat': 'in_playlist', 'noplaylist': True}) as ydl:
        yt_info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        return [entry for entry in (yt_info or {}).get('entries') or [] if entry]


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


def get_cached_track_path(url):
    # Playing from the already-downloaded local file avoids real-time network jitter causing playback skips
    cache_path = f"cache/{str_hash_sha256(url)}.m4a"
    return cache_path if os.path.exists(cache_path) else None

def get_ydl_opts(query=None):
    cache_tpl = f"cache/{str_hash_sha256(query)}" if query is not None else ''
    normalized_path = os.path.join('normalized', cache_tpl)
    if os.path.exists(f'{normalized_path}.m4a'):
        cache_tpl = normalized_path
        warn(None, f'Normalized file in "{normalized_path}" does exist!')
    else:
        warn(None, f'Normalized file in "{normalized_path}" does not exist!')
    return {
        'format': 'm4a/bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a'
        }],
        'noplaylist': True,
        'outtmpl': cache_tpl
    }