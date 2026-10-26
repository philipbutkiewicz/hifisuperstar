#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import os
import re

from yt_dlp.networking.exceptions import TransportError
from yt_dlp.utils import DownloadError


class MediaNotFoundError(Exception):
    """Nothing matched the request (e.g. an empty YouTube search)."""


def _cookies_configured():
    return bool(os.environ.get("HIFI_YOUTUBE_COOKIE_FILE"))


_NO_COOKIES = " No YouTube cookie file is configured for the bot, an admin needs to set one up (see the README)."
_COOKIES_REJECTED = (
    " The bot does have cookies configured, but YouTube did not accept them: they may have expired, "
    "or the account is not logged in / not age-verified. An admin needs to export fresh cookies and restart the bot."
)


def _bot_check_reason():
    return "YouTube is asking the bot to prove it is not a bot." + (
        _COOKIES_REJECTED if _cookies_configured() else _NO_COOKIES
    )


def _age_reason():
    return "the video is age-restricted (18+), so YouTube only serves it to a logged-in adult account." + (
        _COOKIES_REJECTED if _cookies_configured() else _NO_COOKIES
    )


# (substrings of the lowercased yt-dlp message, explanation or a function building it), first match wins
_YOUTUBE_REASONS = (
    (
        ("not a bot", "confirm you’re not a bot", "confirm you're not a bot"),
        _bot_check_reason,
    ),
    (
        (
            "confirm your age",
            "age-restricted",
            "age restricted",
            "inappropriate for some users",
        ),
        _age_reason,
    ),
    (
        ("private video",),
        "the video is private.",
    ),
    (
        ("members-only", "members only", "join this channel", "music premium"),
        "the video is only available to channel members or premium subscribers.",
    ),
    (
        ("copyright",),
        "the video is blocked on copyright grounds.",
    ),
    (
        (
            "not made this video available in your country",
            "blocked it in your country",
            "not available in your country",
            "geo restriction",
            "geo-restricted",
        ),
        "the video is not available in the bot's country (region-locked).",
    ),
    (
        (
            "playback on other websites has been disabled",
            "embedding",
            "uploader has not made this video available",
        ),
        "the uploader has disabled playback outside YouTube, so it can't be downloaded.",
    ),
    (
        ("live event will begin", "premieres in", "this live event"),
        "the video is an upcoming live stream or premiere that has not started yet.",
    ),
    (
        ("has been removed", "removed by the uploader", "account associated with this video has been terminated"),
        "the video was removed by the uploader or YouTube.",
    ),
    (
        ("video unavailable", "this video is not available", "this video isn't available"),
        "the video is unavailable (it may have been deleted).",
    ),
    (
        ("http error 429", "too many requests"),
        "YouTube is rate-limiting the bot. Try again in a few minutes.",
    ),
    (
        ("requested format is not available",),
        "YouTube has no downloadable audio for this video.",
    ),
    (
        ("unsupported url", "is not a valid url"),
        "that link is not something I can play.",
    ),
)


def _clean(message):
    message = re.sub(r"\x1b\[[0-9;]*m", "", str(message))
    # "ERROR: [youtube] abc123: Video unavailable" -> "Video unavailable"
    message = re.sub(r"^\s*ERROR:\s*", "", message)
    message = re.sub(r"^\[[\w:]+\]\s*[\w-]*:\s*", "", message)
    return " ".join(message.split())


def describe_media_error(exc):
    """Turns an exception from looking up/downloading media into a short reason for the user."""
    # Imported lazily: the module is also used by code that does not need the requests stack
    from hifisuperstar.core.Music.MediaSourceProcessing.Direct import (
        MediaValidationError,
    )

    if isinstance(exc, (MediaNotFoundError, MediaValidationError)):
        return str(exc)

    if isinstance(exc, (TimeoutError, ConnectionError, TransportError)):
        return "the connection to the media server timed out or was interrupted. Try again."

    message = _clean(exc)
    lowered = message.lower()
    if isinstance(exc, DownloadError) or "youtube" in lowered:
        for markers, reason in _YOUTUBE_REASONS:
            if any(marker in lowered for marker in markers):
                return reason() if callable(reason) else reason

    if not message:
        return f"an unexpected {type(exc).__name__} occurred."

    return message[:200] + ("…" if len(message) > 200 else "")
