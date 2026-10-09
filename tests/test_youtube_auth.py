#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import os
import tempfile
import unittest
from unittest.mock import patch

from yt_dlp import YoutubeDL

from hifisuperstar.cogs.Music.MusicCog import (
    download_and_cache_youtube_track,
    resolve_track_cache_url,
)
from hifisuperstar.core.Music.MediaSourceProcessing import YouTube


class YouTubeAuthTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cookie_file = os.path.join(self.directory.name, "youtube.txt")
        with open(self.cookie_file, "w") as cookies:
            cookies.write("# Netscape HTTP Cookie File\n")
        environment = patch.dict(
            os.environ, {"HIFI_YOUTUBE_COOKIE_FILE": self.cookie_file}
        )
        environment.start()
        self.addCleanup(environment.stop)

    def test_auth_is_optional(self):
        with patch.dict(os.environ, {"HIFI_YOUTUBE_COOKIE_FILE": ""}):
            self.assertNotIn("cookiefile", YouTube.get_youtube_opts())
            self.assertNotIn("cookiefile", YouTube.get_ydl_opts())
        with patch.dict(os.environ, {}, clear=True):
            self.assertNotIn("cookiefile", YouTube.get_youtube_opts())

    def test_configured_cookie_file_is_passed_to_ydl(self):
        self.assertEqual(YouTube.get_youtube_opts()["cookiefile"], self.cookie_file)
        for query in (None, "https://youtube.com/watch?v=example"):
            with self.subTest(query=query):
                opts = YouTube.get_ydl_opts(query)
                self.assertEqual(opts["cookiefile"], self.cookie_file)
                self.assertEqual(opts["format"], "m4a/bestaudio/best")
                self.assertTrue(opts["noplaylist"])

    def test_missing_cookie_file_is_rejected_before_ydl_can_create_it(self):
        for path in (
            os.path.join(self.directory.name, "missing.txt"),
            self.directory.name,
        ):
            with (
                self.subTest(path=path),
                patch.dict(os.environ, {"HIFI_YOUTUBE_COOKIE_FILE": path}),
                self.assertRaisesRegex(FileNotFoundError, "HIFI_YOUTUBE_COOKIE_FILE"),
            ):
                YouTube.get_youtube_opts()

    def test_yt_dlp_loads_the_configured_cookie_file(self):
        with open(self.cookie_file, "a") as cookies:
            cookies.write(".youtube.com\tTRUE\t/\tTRUE\t2147483647\ttest\tdummy\n")
        with YoutubeDL(YouTube.get_youtube_opts()) as ydl:
            self.assertEqual(
                [(cookie.name, cookie.value) for cookie in ydl.cookiejar],
                [("test", "dummy")],
            )

    def test_javascript_runtimes_are_enabled_without_cookies(self):
        with patch.dict(os.environ, {"HIFI_YOUTUBE_COOKIE_FILE": ""}):
            opts = YouTube.get_youtube_opts()
            self.assertEqual(opts["js_runtimes"], {"deno": {}, "node": {}})
            with YoutubeDL(opts) as ydl:
                self.assertEqual(ydl.params["js_runtimes"], opts["js_runtimes"])

    def test_playback_and_cache_download_use_cookies(self):
        url = "https://youtube.com/watch?v=example"
        track_info = {"id": "example"}
        with (
            patch.object(YouTube, "YoutubeDL") as factory,
            patch.object(YouTube, "download_youtube_media") as download,
            patch.object(YouTube, "get_cached_track_path", return_value=None),
            patch.object(YouTube, "get_best_audio_url", return_value="audio"),
        ):
            ydl = factory.return_value.__enter__.return_value
            ydl.extract_info.return_value = track_info
            self.assertEqual(YouTube.media_get_youtube_direct(url)[1:], (url, "audio"))
            ydl.extract_info.return_value = {"entries": [track_info]}
            self.assertEqual(
                YouTube.media_get_youtube_query("song")[1:], (url, "audio")
            )
            self.assertEqual(download.call_count, 2)
            YouTube.download_youtube_media_thread(url)
            ydl.download.assert_called_once_with([url])
            for call in factory.call_args_list:
                self.assertEqual(call.args[0]["cookiefile"], self.cookie_file)
                self.assertEqual(call.args[0]["js_runtimes"], {"deno": {}, "node": {}})

    def test_search_and_playlist_pages_use_cookies(self):
        with patch.object(YouTube, "YoutubeDL") as factory:
            ydl = factory.return_value.__enter__.return_value
            ydl.extract_info.return_value = {"entries": [{"id": "example"}, None]}
            self.assertEqual(YouTube.media_search_youtube("song"), [{"id": "example"}])
            self.assertEqual(factory.call_args.args[0]["extract_flat"], "in_playlist")

            first_page = [{"id": str(index)} for index in range(100)]
            ydl.extract_info.side_effect = [
                {"entries": first_page},
                {"entries": [{"id": "last"}]},
            ]
            self.assertEqual(
                YouTube.media_get_youtube_playlist("playlist"),
                first_page + [{"id": "last"}],
            )
            self.assertEqual(factory.call_args.args[0]["playliststart"], 101)
            self.assertFalse(factory.call_args.args[0]["noplaylist"])
            for call in factory.call_args_list:
                self.assertEqual(call.args[0]["cookiefile"], self.cookie_file)
                self.assertEqual(call.args[0]["js_runtimes"], {"deno": {}, "node": {}})

    def test_playlist_download_lookup_and_download_use_cookies(self):
        with patch("hifisuperstar.cogs.Music.MusicCog.YoutubeDL") as factory:
            ydl = factory.return_value.__enter__.return_value
            ydl.extract_info.return_value = {"entries": [{"id": "example"}]}
            url = resolve_track_cache_url("song")
            self.assertEqual(url, "https://youtube.com/watch?v=example")
            download_and_cache_youtube_track(url)
            ydl.download.assert_called_once_with([url])
            for call in factory.call_args_list:
                self.assertEqual(call.args[0]["cookiefile"], self.cookie_file)
                self.assertEqual(call.args[0]["js_runtimes"], {"deno": {}, "node": {}})


if __name__ == "__main__":
    unittest.main()
