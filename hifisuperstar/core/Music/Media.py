#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

from urllib.parse import parse_qs, urlparse

import validators

from hifisuperstar.core.Music.MediaSourceProcessing.Direct import media_get_direct
from hifisuperstar.core.Music.MediaSourceProcessing.YouTube import (
    media_get_youtube_direct,
    media_get_youtube_playlist,
    media_get_youtube_query,
)
from hifisuperstar.io.Logger import error, info


# TODO: M3U playlists
_YOUTUBE_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def is_youtube_domain(url):
    return (urlparse(url).hostname or "").lower() in _YOUTUBE_DOMAINS


def media_get_playlist(url, errors=None):
    info(None, f"Media: Fetching YouTube playlist '{url}'...")

    if not validators.url(url):
        error(None, "Media: Invalid URL!")
        if errors is not None:
            errors.append("that is not a valid link.")
        return False

    if not is_youtube_domain(url):
        error(None, "Media: Invalid domain!")
        if errors is not None:
            errors.append("only YouTube playlist links are supported.")
        return False

    # URLs with both 'v' (a specific video) and 'list' make YouTube/yt-dlp start listing from that
    # video's position instead of the beginning, truncating the results, so normalize to the plain
    # playlist URL to always fetch the full list from the start.
    list_id = parse_qs(urlparse(url).query).get("list", [None])[0]
    if list_id:
        url = f"https://www.youtube.com/playlist?list={list_id}"

    return media_get_youtube_playlist(url, errors)


def media_get_source(query, allowed_mime_types=None):
    if validators.url(query):
        if is_youtube_domain(query):
            return media_get_youtube_direct(query)
        else:
            return media_get_direct(query, allowed_mime_types)
    else:
        return media_get_youtube_query(query)
