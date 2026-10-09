#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import json
import os
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.networking.exceptions import TransportError
from yt_dlp.utils import DownloadError

from hifisuperstar.io.Logger import error, info, warn
from hifisuperstar.io.Strings import str_hash_sha256

_download_locks = {}
_download_locks_guard = threading.Lock()


def extract_youtube_info(ydl, query, *, download=False):
    retries = 0
    while True:
        try:
            return ydl.extract_info(query, download=download)
        except (DownloadError, TransportError, TimeoutError, ConnectionError) as exc:
            if retries == 3:
                raise
            retries += 1
            warn(
                None,
                f"YouTube: Fetch failed for '{query}' - {exc}. "
                f"Retry {retries}/3 in 5 seconds",
            )
            time.sleep(5)


def media_get_youtube_direct(url):
    cached = get_cached_youtube_source(url)
    if cached is not None:
        return cached

    info(None, f"YouTube: Extracting YouTube link info for query '{url}'...")
    with YoutubeDL(get_ydl_opts()) as ydl:
        yt_info = extract_youtube_info(ydl, url)

        track_info = {"info": yt_info, "is_youtube": True}
        cache_youtube_info(url, url, yt_info)

        if get_cached_track_path(url) is None:
            download_youtube_media(url)

        return (
            track_info,
            url,
            get_cached_track_path(url) or get_best_audio_url(yt_info),
        )


def media_get_youtube_query(query):
    cached = get_cached_youtube_source(query)
    if cached is not None:
        return cached

    info(None, f"YouTube: Performing a YouTube search for query '{query}'...")
    with YoutubeDL(get_ydl_opts()) as ydl:
        yt_info = extract_youtube_info(ydl, f"ytsearch:{query}")["entries"][0]

        track_info = {"info": yt_info, "is_youtube": True}

        url = f"https://youtube.com/watch?v={yt_info['id']}"
        cache_youtube_info(query, url, yt_info)

        if get_cached_track_path(url) is None:
            download_youtube_media(url)

        return (
            track_info,
            url,
            get_cached_track_path(url) or get_best_audio_url(yt_info),
        )


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
                **get_youtube_opts(),
                "quiet": True,
                "ignoreerrors": "only_download",
                "extract_flat": "in_playlist",
                "noplaylist": False,
                "playliststart": start,
                "playlistend": start + page_size - 1,
                "extractor_retries": 10,
                "socket_timeout": 30,
            }

            with YoutubeDL(ydl_opts) as ydl:
                yt_info = extract_youtube_info(ydl, url)

            page_entries = (yt_info or {}).get("entries") or []
            entries.extend(page_entries)

            if len(page_entries) < page_size:
                break

            start += page_size

        return entries
    except Exception as e:
        error(None, f"YouTube: Failed to fetch playlist '{url}' - {e!s}")
        return None


def media_search_youtube(query, limit=25):
    info(None, f"YouTube: Searching for '{query}' (limit {limit})...")
    with YoutubeDL(
        {
            **get_youtube_opts(),
            "quiet": True,
            "extract_flat": "in_playlist",
            "noplaylist": True,
        }
    ) as ydl:
        yt_info = extract_youtube_info(ydl, f"ytsearch{limit}:{query}")
        return [entry for entry in (yt_info or {}).get("entries") or [] if entry]


def download_youtube_media(url):
    info(None, f"YouTube: Starting cache download thread for '{url}'...")
    thread = threading.Thread(target=download_youtube_media_thread, args=(url,))
    thread.start()


def download_youtube_media_thread(url):
    try:
        download_and_cache_youtube_media(url)
    except Exception as exc:
        error(
            None,
            f"YouTube: Cache download failed for '{url}' - {exc}. Download will be resumed the next time this track is played",
        )


def download_and_cache_youtube_media(url):
    with _download_locks_guard:
        lock = _download_locks.setdefault(canonical_youtube_url(url), threading.Lock())
    with lock:
        if get_cached_track_path(url) is not None:
            return
        with YoutubeDL(get_ydl_opts(url)) as ydl:
            yt_info = extract_youtube_info(ydl, url, download=True)
            cache_youtube_info(url, url, yt_info)


def precache_youtube_track(query):
    if get_cached_youtube_source(query) is not None:
        return False

    cached = get_cached_youtube_info(query)
    parsed = urlparse(query)
    is_url = parsed.scheme in ("http", "https")
    url = query if is_url else cached["url"] if cached is not None else None
    downloaded = False
    if cached is None:
        if is_url and get_cached_track_path(url) is None:
            download_and_cache_youtube_media(url)
            downloaded = True
        else:
            with YoutubeDL(get_ydl_opts()) as ydl:
                yt_info = extract_youtube_info(
                    ydl, query if is_url else f"ytsearch:{query}"
                )
                if not is_url:
                    yt_info = yt_info["entries"][0]
                    url = f"https://youtube.com/watch?v={yt_info['id']}"
                cache_youtube_info(query, url, yt_info)

    if not downloaded:
        download_and_cache_youtube_media(url)
    if get_cached_youtube_source(query) is None:
        raise RuntimeError(
            f"Audio or metadata is still missing after caching '{query}'"
        )
    return True


def get_best_audio_url(yt_info):
    best_format = None
    for format in yt_info["formats"]:
        if (
            format["resolution"] == "audio only"
            and format["ext"] == "m4a"
            and (best_format == None or best_format["quality"] < format["quality"])
        ):
            best_format = format

    return None if best_format is None else best_format["url"]


def get_cached_track_path(url):
    # Playing from the already-downloaded local file avoids real-time network jitter causing playback skips
    keys = dict.fromkeys((url, canonical_youtube_url(url)))
    for directory in ("normalized/cache", "cache"):
        for key in keys:
            path = os.path.join(directory, f"{str_hash_sha256(key)}.m4a")
            if os.path.isfile(path):
                return path
    return None


def canonical_youtube_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    video_id = None
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
            video_id = parsed.path.split("/")[2]
    if video_id:
        return f"https://youtube.com/watch?v={video_id}"
    return url


def get_cached_youtube_info(query):
    path = f"cache/{str_hash_sha256(canonical_youtube_url(query))}.info.json"
    try:
        with open(path, encoding="utf-8") as file:
            cached = json.load(file)
        if (
            not isinstance(cached, dict)
            or not isinstance(cached.get("url"), str)
            or not isinstance(cached.get("info"), dict)
            or not isinstance(cached["info"].get("id"), str)
            or not isinstance(cached["info"].get("title"), str)
        ):
            raise TypeError("Missing or invalid track metadata")
        return cached
    except FileNotFoundError:
        return None
    except (OSError, TypeError, ValueError) as exc:
        warn(None, f"YouTube: Could not read cached metadata '{path}' - {exc}")
        return None


def cache_youtube_info(query, url, yt_info):
    # Stream URLs and request headers expire and may contain authentication data.
    fields = (
        "id",
        "title",
        "duration",
        "thumbnail",
        "description",
        "uploader",
        "uploader_id",
        "channel",
        "channel_id",
        "webpage_url",
        "upload_date",
        "view_count",
        "like_count",
        "artist",
        "album",
        "track",
    )
    metadata = {key: yt_info[key] for key in fields if key in yt_info}
    if not isinstance(metadata.get("id"), str) or not isinstance(
        metadata.get("title"), str
    ):
        warn(None, f"YouTube: Cannot cache incomplete metadata for '{url}'")
        return
    cached = {"url": url, "info": metadata}
    for key in dict.fromkeys(
        (canonical_youtube_url(query), canonical_youtube_url(url))
    ):
        path = f"cache/{str_hash_sha256(key)}.info.json"
        temporary_path = None
        try:
            os.makedirs("cache", exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir="cache", suffix=".tmp", delete=False
            ) as file:
                temporary_path = file.name
                json.dump(cached, file)
            os.replace(temporary_path, path)
        except (OSError, TypeError, ValueError) as exc:
            warn(None, f"YouTube: Could not write cached metadata '{path}' - {exc}")
        finally:
            if temporary_path is not None and os.path.exists(temporary_path):
                os.unlink(temporary_path)


def get_cached_youtube_source(query):
    cached = get_cached_youtube_info(query)
    if cached is None:
        return None
    audio_path = get_cached_track_path(query) or get_cached_track_path(cached["url"])
    if audio_path is None:
        return None
    info(None, f"YouTube: Playing cached track '{cached['info']['title']}'")
    return {"info": cached["info"], "is_youtube": True}, cached["url"], audio_path


def get_youtube_opts() -> dict[str, object]:
    opts: dict[str, object] = {"js_runtimes": {"deno": {}, "node": {}}}
    cookie_file = os.environ.get("HIFI_YOUTUBE_COOKIE_FILE")
    if not cookie_file:
        return opts
    if not os.path.isfile(cookie_file):
        raise FileNotFoundError(
            f"HIFI_YOUTUBE_COOKIE_FILE must point to an existing cookie file: {cookie_file}"
        )
    opts["cookiefile"] = cookie_file
    return opts


def get_ydl_opts(query=None):
    cache_tpl = (
        f"cache/{str_hash_sha256(canonical_youtube_url(query))}"
        if query is not None
        else ""
    )
    normalized_path = os.path.join("normalized", cache_tpl)
    if os.path.exists(f"{normalized_path}.m4a"):
        cache_tpl = normalized_path
        warn(None, f'Normalized file in "{normalized_path}" does exist!')
    else:
        warn(None, f'Normalized file in "{normalized_path}" does not exist!')
    return {
        **get_youtube_opts(),
        "format": "m4a/bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
        "noplaylist": True,
        "outtmpl": cache_tpl,
    }
