# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import validators
from hifisuperstar.core.Music.MediaSourceProcessing.Direct import media_get_direct
from hifisuperstar.core.Music.MediaSourceProcessing.YouTube import media_get_youtube_direct
from hifisuperstar.core.Music.MediaSourceProcessing.YouTube import media_get_youtube_playlist
from hifisuperstar.core.Music.MediaSourceProcessing.YouTube import media_get_youtube_query
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import error
from urllib.parse import urlparse
from urllib.parse import parse_qs


# TODO: M3U playlists
def media_get_playlist(url):
    info(None, f"Media: Fetching YouTube playlist '{url}'...")

    if not validators.url(url):
        error(None, 'Media: Invalid URL!')
        return False

    domain = urlparse(url.lower().replace('www.', '')).netloc
    if not domain == 'youtube.com' and not domain == 'youtu.be':
        error(None, 'Media: Invalid domain!')
        return False

    # URLs with both 'v' (a specific video) and 'list' make YouTube/yt-dlp start listing from that
    # video's position instead of the beginning, truncating the results, so normalize to the plain
    # playlist URL to always fetch the full list from the start.
    list_id = parse_qs(urlparse(url).query).get('list', [None])[0]
    if list_id:
        url = f"https://www.youtube.com/playlist?list={list_id}"

    return media_get_youtube_playlist(url)


def media_get_source(query, allowed_mime_types=None):
    if validators.url(query):
        domain = urlparse(query.lower().replace('www.', '')).netloc
        if domain == 'youtube.com' or domain == 'youtu.be':
            return media_get_youtube_direct(query)
        else:
            return media_get_direct(query, allowed_mime_types)
    else:
        return media_get_youtube_query(query)
