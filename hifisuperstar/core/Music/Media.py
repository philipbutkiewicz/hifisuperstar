# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import validators
import requests
import threading
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import warn
from hifisuperstar.io.Logger import error
from hifisuperstar.io.Strings import str_hash_sha256
from yt_dlp import YoutubeDL
from urllib.parse import urlparse


def media_get_playlist(url):
    info(None, f"Media: Fetching YouTube playlist '{url}'...")

    if not validators.url(url):
        error(None, 'Media: Invalid URL!')
        return False

    domain = urlparse(url.lower().replace('www.', '')).netloc
    if not domain == 'youtube.com' and not domain == 'youtu.be':
        error(None, 'Media: Invalid domain!')
        return False
    
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a'
        }],
        'download': False
    }

    with YoutubeDL(ydl_opts) as ydl:
        yt_info = ydl.extract_info(url, False)
        return yt_info['entries']


def media_get_source(query, refresh_cache=False, allowed_mime_types=None):
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a'
        }],
        'noplaylist': True,
        'outtmpl': f"cache/{str_hash_sha256(query)}"
    }
        
    with YoutubeDL(ydl_opts) as ydl:
        if validators.url(query):
            domain = urlparse(query.lower().replace('www.', '')).netloc
            if domain == 'youtube.com' or domain == 'youtu.be':
                return media_get_youtube_direct(ydl, query)
            else:
                return media_get_direct(query, allowed_mime_types)
        else:
            return media_get_youtube_query(ydl, query)


def media_get_direct(url, allowed_mime_types=None):
    info(None, f"Media: Extracting media link info for URL '{url}'...")

    track_info = {
        'is_youtube': False
    }

    media_check_url(url, allowed_mime_types)

    return track_info, url, url


def media_get_youtube_direct(ydl, url):
    info(None, f"Media: Extracting YouTube link info for query '{url}'...")
    yt_info = ydl.extract_info(url, download=False)

    track_info = {
        'info': yt_info,
        'is_youtube': True
    }

    download_youtube_media(url)

    return track_info, url, get_best_audio_url(yt_info)


def media_get_youtube_query(ydl, query):
    info(None, f"Media: Performing a YouTube search for query '{query}'...")
    yt_info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]

    track_info = {
        'info': yt_info,
        'is_youtube': True
    }

    url = f"https://youtube.com/watch?v={yt_info['id']}"

    download_youtube_media(url)

    return track_info, url, get_best_audio_url(yt_info)


def media_check_url(url, allowed_mime_types=None):
    info(None, f"Media: Checking media URL '{url}'...")

    res = requests.get(url)
    content_type = res.headers['Content-Type']
    if allowed_mime_types and content_type not in allowed_mime_types:
        warn(None, f"Media: Invalid content type '{content_type}' for URL '{url}'!")
        raise Exception(f"MIME type {content_type} is not allowed")

def download_youtube_media(url, orig_query=None):
    info(None, f"Media: Starting cache download thread for '{url}'...")
    cache_url = f"cache/{str_hash_sha256(orig_query if orig_query is not None else url)}"
    thread = threading.Thread(target=download_youtube_media_thread, args=(url, cache_url))
    thread.start()

def download_youtube_media_thread(url, cache_url):
    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a'
        }],
        'noplaylist': True,
        'outtmpl': cache_url
    }

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def get_best_audio_url(yt_info):
    best_format = None
    for format in yt_info['formats']:
        if format['resolution'] == 'audio only' and format['ext'] == 'm4a' and (best_format == None or best_format['quality'] < format['quality']):
            best_format = format
        
    return None if best_format is None else best_format['url']