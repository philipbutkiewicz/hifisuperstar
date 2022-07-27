# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2022 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import validators
import requests
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import warn
from hifisuperstar.io.Logger import error
from youtube_dl import YoutubeDL
from urllib.parse import urlparse


def media_check_url(url, allowed_mime_types=None):
    info(None, f"Media: Checking media URL '{url}'...")

    res = requests.get(url)
    content_type = res.headers['Content-Type']
    if allowed_mime_types and content_type not in allowed_mime_types:
        warn(None, f"Media: Invalid content type '{content_type}' for URL '{url}'!")
        raise Exception(f"MIME type {content_type} is not allowed")


def media_get_source(query, allowed_mime_types=None):
    with YoutubeDL({'format': 'bestaudio', 'noplaylist': True, 'username': 'test', 'password': 'test'}) as ydl:
        if validators.url(query):
            domain = urlparse(query.lower().replace('www.', '')).netloc
            if domain == 'youtube.com' or domain == 'youtu.be':
                info(None, f"Media: Extracting YouTube link info for query '{query}'...")
                yt_info = ydl.extract_info(query, download=False)

                url = yt_info['formats'][0]['url']
                track_info = {
                    'info': yt_info,
                    'is_youtube': True
                }
            else:
                info(None, f"Media: Extracting media link info for query '{query}'...")
                track_info = {
                    'is_youtube': False
                }
                url = query

                media_check_url(url, allowed_mime_types)
        else:
            info(None, f"Media: Performing a YouTube search for query '{query}'...")
            yt_info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]

            url = yt_info['formats'][0]['url']
            track_info = {
                'info': yt_info,
                'is_youtube': True
            }

    return track_info, url


def media_get_playlist(url):
    info(None, f"Media: Fetching YouTube playlist '{url}'...")

    if not validators.url(url):
        error(None, 'Media: Invalid URL!')
        return False

    domain = urlparse(url.lower().replace('www.', '')).netloc
    if not domain == 'youtube.com' and not domain == 'youtu.be':
        error(None, 'Media: Invalid domain!')
        return False

    with YoutubeDL({'format': 'bestaudio', 'noplaylist': False, 'username': 'test', 'password': 'test',
                    'ignoreerrors': True, 'download': False}) as ydl:
        yt_info = ydl.extract_info(url, False)
        return yt_info['entries']
