# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import requests
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import warn


def media_get_direct(url, allowed_mime_types=None):
    info(None, f"Media: Extracting media link info for URL '{url}'...")

    track_info = {
        'is_youtube': False
    }

    media_check_url(url, allowed_mime_types)

    return track_info, url, url


def media_check_url(url, allowed_mime_types=None):
    info(None, f"Media: Checking media URL '{url}'...")

    res = requests.get(url)
    content_type = res.headers['Content-Type']
    if allowed_mime_types and content_type not in allowed_mime_types:
        warn(None, f"Media: Invalid content type '{content_type}' for URL '{url}'!")
        raise Exception(f"MIME type {content_type} is not allowed")
