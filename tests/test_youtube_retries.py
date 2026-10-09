import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from yt_dlp.networking.exceptions import TransportError
from yt_dlp.utils import DownloadError

from hifisuperstar.cogs.Music.MusicCog import resolve_track_cache_url
from hifisuperstar.core.Music.MediaSourceProcessing import YouTube
from hifisuperstar.io.Strings import str_hash_sha256


class YouTubeRetryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        previous_directory = os.getcwd()
        os.chdir(directory.name)
        self.addCleanup(os.chdir, previous_directory)
        self.url = "https://youtube.com/watch?v=example"
        self.track = {"id": "example", "title": "Example"}
        sleep = patch.object(YouTube.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)
        warn = patch.object(YouTube, "warn")
        self.warn = warn.start()
        self.addCleanup(warn.stop)

    def test_success_does_not_retry_or_sleep(self):
        ydl = Mock()
        ydl.extract_info.return_value = self.track
        self.assertIs(YouTube.extract_youtube_info(ydl, self.url), self.track)
        ydl.extract_info.assert_called_once_with(self.url, download=False)
        self.sleep.assert_not_called()
        self.warn.assert_not_called()

    def test_three_retries_wait_five_seconds_and_preserve_download_flag(self):
        for failure in (
            TimeoutError("read timed out"),
            TransportError("read timed out"),
            DownloadError("HTTP Error 403: Forbidden"),
            ConnectionError("connection reset"),
        ):
            with self.subTest(failure=failure):
                self.sleep.reset_mock()
                self.warn.reset_mock()
                ydl = Mock()
                ydl.extract_info.side_effect = [failure] * 3 + [self.track]
                self.assertIs(
                    YouTube.extract_youtube_info(ydl, self.url, download=True),
                    self.track,
                )
                self.assertEqual(
                    ydl.extract_info.call_args_list,
                    [call(self.url, download=True)] * 4,
                )
                self.assertEqual(self.sleep.call_args_list, [call(5)] * 3)
                self.assertEqual(self.warn.call_count, 3)

    def test_exhaustion_raises_original_error_without_a_final_sleep(self):
        failure = DownloadError("HTTP Error 403: Forbidden")
        ydl = Mock()
        ydl.extract_info.side_effect = failure
        with self.assertRaises(DownloadError) as raised:
            YouTube.extract_youtube_info(ydl, self.url)
        self.assertIs(raised.exception, failure)
        self.assertEqual(ydl.extract_info.call_count, 4)
        self.assertEqual(self.sleep.call_args_list, [call(5)] * 3)

    def test_recovery_stops_retrying_immediately(self):
        ydl = Mock()
        ydl.extract_info.side_effect = [TimeoutError("read timed out"), self.track]
        self.assertIs(YouTube.extract_youtube_info(ydl, self.url), self.track)
        self.assertEqual(ydl.extract_info.call_count, 2)
        self.sleep.assert_called_once_with(5)

    def test_programming_errors_are_not_retried(self):
        ydl = Mock()
        ydl.extract_info.side_effect = TypeError("invalid argument")
        with self.assertRaises(TypeError):
            YouTube.extract_youtube_info(ydl, self.url)
        self.assertEqual(ydl.extract_info.call_count, 1)
        self.sleep.assert_not_called()

    def test_all_fetch_paths_recover_after_three_failures(self):
        paths = (
            ("direct", lambda: YouTube.media_get_youtube_direct(self.url)),
            ("query", lambda: YouTube.media_get_youtube_query("song")),
            ("search", lambda: YouTube.media_search_youtube("song")),
            ("playlist", lambda: YouTube.media_get_youtube_playlist("playlist")),
            ("download", lambda: YouTube.download_and_cache_youtube_media(self.url)),
            ("precache-url", lambda: YouTube.precache_youtube_track(self.url)),
            ("precache-query", lambda: YouTube.precache_youtube_track("song")),
            ("export-query", lambda: resolve_track_cache_url("song")),
        )
        for name, fetch in paths:
            with (
                self.subTest(path=name),
                tempfile.TemporaryDirectory() as directory,
                patch.object(YouTube, "YoutubeDL") as factory,
                patch("hifisuperstar.cogs.Music.MusicCog.YoutubeDL", factory),
                patch.object(YouTube, "download_youtube_media"),
                patch.object(YouTube, "get_best_audio_url", return_value="audio"),
            ):
                previous_directory = os.getcwd()
                os.chdir(directory)
                try:
                    self.sleep.reset_mock()
                    ydl = factory.return_value.__enter__.return_value
                    attempts = 0

                    def extract(query, download):
                        nonlocal attempts
                        attempts += 1
                        if attempts <= 3:
                            raise DownloadError("HTTP Error 403: Forbidden")
                        if download:
                            Path("cache").mkdir(exist_ok=True)
                            Path(f"cache/{str_hash_sha256(self.url)}.m4a").write_bytes(
                                b"audio"
                            )
                        if query.startswith("ytsearch") or query == "playlist":
                            return {"entries": [self.track]}
                        return self.track

                    ydl.extract_info.side_effect = extract
                    result = fetch()
                    if name == "download":
                        self.assertIsNone(result)
                        self.assertIsNotNone(YouTube.get_cached_youtube_source(self.url))
                    else:
                        self.assertIsNotNone(result)
                    self.assertEqual(
                        ydl.extract_info.call_count,
                        5 if name == "precache-query" else 4,
                    )
                    self.assertEqual(self.sleep.call_args_list, [call(5)] * 3)
                finally:
                    os.chdir(previous_directory)

    def test_playlist_exhaustion_keeps_existing_error_handling(self):
        with (
            patch.object(YouTube, "YoutubeDL") as factory,
            patch.object(YouTube, "error") as error,
        ):
            ydl = factory.return_value.__enter__.return_value
            ydl.extract_info.side_effect = DownloadError("HTTP Error 403: Forbidden")
            self.assertIsNone(YouTube.media_get_youtube_playlist("playlist"))
            self.assertEqual(ydl.extract_info.call_count, 4)
            error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
