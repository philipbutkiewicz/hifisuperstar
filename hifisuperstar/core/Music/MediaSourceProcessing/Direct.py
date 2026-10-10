#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

from hifisuperstar.io.Logger import info, warn

_ALLOWED_SCHEMES = {"http", "https"}
_REQUEST_TIMEOUT = 10  # seconds
_MAX_REDIRECTS = 5


class MediaValidationError(Exception):
    pass


def media_get_direct(url, allowed_mime_types=None):
    info(None, f"Media: Extracting media link info for URL '{url}'...")

    track_info = {"is_youtube": False}

    media_check_url(url, allowed_mime_types)

    return track_info, url, url


def _assert_public_host(url):
    """Refuses URLs pointing at loopback/private/link-local addresses (SSRF protection)."""
    hostname = urlparse(url).hostname
    if not hostname:
        raise MediaValidationError("URL has no host")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise MediaValidationError(f"Could not resolve host '{hostname}'") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global:
            raise MediaValidationError("URL points to a non-public address")


def media_check_url(url, allowed_mime_types=None):
    info(None, f"Media: Checking media URL '{url}'...")

    current_url = url
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = urlparse(current_url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            raise MediaValidationError(f"URL scheme '{parsed.scheme}' is not allowed")
        _assert_public_host(current_url)

        # stream=True: only the headers are needed, never download the media body
        with requests.get(
            current_url, timeout=_REQUEST_TIMEOUT, allow_redirects=False, stream=True
        ) as res:
            if res.is_redirect and res.headers.get("Location"):
                current_url = urljoin(current_url, res.headers["Location"])
                continue
            content_type = res.headers.get("Content-Type", "")
            break
    else:
        raise MediaValidationError("Too many redirects")

    mime_type = content_type.split(";")[0].strip().lower()
    if allowed_mime_types and mime_type not in {m.lower() for m in allowed_mime_types}:
        warn(None, f"Media: Invalid content type '{content_type}' for URL '{url}'!")
        raise MediaValidationError(f"MIME type {content_type} is not allowed")
