import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hifisuperstar.cogs.Music.MusicCog import (
    MusicCog,
    download_and_cache_youtube_track,
    resolve_track_cache_url,
)
from hifisuperstar.core.Music.Media import media_get_source
from hifisuperstar.core.Music.MediaSourceProcessing import YouTube
from hifisuperstar.io.Strings import str_hash_sha256


class YouTubeCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        previous_directory = os.getcwd()
        os.chdir(self.directory.name)
        self.addCleanup(os.chdir, previous_directory)
        Path("cache").mkdir()
        self.url = "https://youtube.com/watch?v=iw63L_BIoMw"
        self.track = {
            "id": "iw63L_BIoMw",
            "title": "Example song",
            "duration": 123,
            "url": "expired-stream",
            "formats": [{"url": "expired-format"}],
            "http_headers": {"Cookie": "do-not-cache"},
        }
        self.audio_path = f"cache/{str_hash_sha256(self.url)}.m4a"
        self.info_path = f"cache/{str_hash_sha256(self.url)}.info.json"

    def seed_cache(self, query=None):
        Path(self.audio_path).write_bytes(b"cached audio")
        YouTube.cache_youtube_info(query or self.url, self.url, self.track)

    def test_cached_playback_returns_metadata_and_audio_without_youtube(self):
        self.seed_cache()
        with (
            patch.object(YouTube, "YoutubeDL") as factory,
            patch.object(YouTube, "download_youtube_media") as download,
            patch.dict(os.environ, {"HIFI_YOUTUBE_COOKIE_FILE": "/missing/cookies"}),
        ):
            track_info, url, path = media_get_source(self.url)
            factory.assert_not_called()
            download.assert_not_called()
        self.assertTrue(track_info["is_youtube"])
        self.assertEqual(track_info["info"]["title"], self.track["title"])
        self.assertEqual(track_info["info"]["duration"], 123)
        self.assertEqual(url, self.url)
        self.assertEqual(path, self.audio_path)
        self.assertNotIn("formats", track_info["info"])
        self.assertNotIn("url", track_info["info"])
        self.assertNotIn("http_headers", track_info["info"])

    def test_query_resolution_survives_disk_reload(self):
        self.seed_cache("my song")
        with (
            patch.object(YouTube, "YoutubeDL") as factory,
            patch("hifisuperstar.cogs.Music.MusicCog.YoutubeDL") as export_factory,
        ):
            self.assertEqual(
                media_get_source("my song")[1:], (self.url, self.audio_path)
            )
            self.assertEqual(resolve_track_cache_url("my song"), self.url)
            factory.assert_not_called()
            export_factory.assert_not_called()

    def test_url_variants_share_cache_and_normalized_audio_is_preferred(self):
        self.seed_cache()
        normalized_path = os.path.join("normalized", self.audio_path)
        Path(normalized_path).parent.mkdir(parents=True)
        Path(normalized_path).write_bytes(b"normalized audio")
        for url in (
            "https://www.youtube.com/watch?v=iw63L_BIoMw&list=playlist",
            "https://youtu.be/iw63L_BIoMw?t=10",
            "https://youtube.com/shorts/iw63L_BIoMw",
            "https://youtube.com/embed/iw63L_BIoMw",
        ):
            with self.subTest(url=url), patch.object(YouTube, "YoutubeDL") as factory:
                self.assertEqual(
                    YouTube.media_get_youtube_direct(url)[2], normalized_path
                )
                factory.assert_not_called()

    def test_metadata_does_not_require_original_audio_when_normalized_exists(self):
        self.seed_cache()
        normalized_path = os.path.join("normalized", self.audio_path)
        Path(normalized_path).parent.mkdir(parents=True)
        Path(self.audio_path).rename(normalized_path)
        with patch.object(YouTube, "YoutubeDL") as factory:
            self.assertEqual(media_get_source(self.url)[2], normalized_path)
            factory.assert_not_called()

    def test_legacy_exact_url_audio_is_still_found_after_backfill(self):
        url = "https://www.youtube.com/watch?v=iw63L_BIoMw&t=10"
        path = f"cache/{str_hash_sha256(url)}.m4a"
        Path(path).write_bytes(b"legacy audio")
        YouTube.cache_youtube_info(url, url, self.track)
        with patch.object(YouTube, "YoutubeDL") as factory:
            self.assertEqual(media_get_source(url)[2], path)
            self.assertEqual(media_get_source(self.url)[2], path)
            factory.assert_not_called()

    def test_download_template_is_shared_between_url_variants(self):
        with patch.dict(os.environ, {"HIFI_YOUTUBE_COOKIE_FILE": ""}):
            self.assertEqual(
                YouTube.get_ydl_opts("https://youtu.be/iw63L_BIoMw?t=10")["outtmpl"],
                self.audio_path.removesuffix(".m4a"),
            )

    def test_existing_audio_is_backfilled_once_without_redownload(self):
        Path(self.audio_path).write_bytes(b"old audio")
        with (
            patch.object(YouTube, "YoutubeDL") as factory,
            patch.object(YouTube, "download_youtube_media") as download,
        ):
            ydl = factory.return_value.__enter__.return_value
            ydl.extract_info.return_value = self.track
            self.assertEqual(media_get_source(self.url)[2], self.audio_path)
            self.assertEqual(media_get_source(self.url)[2], self.audio_path)
            ydl.extract_info.assert_called_once_with(self.url, download=False)
            download.assert_not_called()
        self.assertTrue(Path(self.info_path).is_file())

    def test_missing_audio_fetches_fresh_info_not_expired_stream_urls(self):
        YouTube.cache_youtube_info(self.url, self.url, self.track)
        with (
            patch.object(YouTube, "YoutubeDL") as factory,
            patch.object(YouTube, "download_youtube_media") as download,
            patch.object(YouTube, "get_best_audio_url", return_value="fresh-stream"),
        ):
            ydl = factory.return_value.__enter__.return_value
            ydl.extract_info.return_value = self.track
            self.assertEqual(media_get_source(self.url)[2], "fresh-stream")
            ydl.extract_info.assert_called_once_with(self.url, download=False)
            download.assert_called_once_with(self.url)

    def test_uncached_query_writes_query_and_url_sidecars(self):
        with (
            patch.object(YouTube, "YoutubeDL") as factory,
            patch.object(YouTube, "download_youtube_media"),
            patch.object(YouTube, "get_best_audio_url", return_value="fresh-stream"),
        ):
            ydl = factory.return_value.__enter__.return_value
            ydl.extract_info.return_value = {"entries": [self.track]}
            self.assertEqual(
                media_get_source("my song")[1:], (self.url, "fresh-stream")
            )
        self.assertEqual(YouTube.get_cached_youtube_info("my song")["url"], self.url)
        self.assertEqual(
            YouTube.get_cached_youtube_info(self.url)["info"]["id"], self.track["id"]
        )

    def test_bad_metadata_is_logged_and_replaced(self):
        for content in ("not json", "null", '{"info": {"title": "bad"}}'):
            with self.subTest(content=content):
                Path(self.info_path).write_text(content)
                Path(self.audio_path).write_bytes(b"audio")
                with (
                    patch.object(YouTube, "warn") as warn,
                    patch.object(YouTube, "YoutubeDL") as factory,
                    patch.object(YouTube, "download_youtube_media") as download,
                ):
                    ydl = factory.return_value.__enter__.return_value
                    ydl.extract_info.return_value = self.track
                    self.assertEqual(media_get_source(self.url)[2], self.audio_path)
                    warn.assert_called()
                    download.assert_not_called()
                self.assertEqual(
                    json.loads(Path(self.info_path).read_text())["info"]["title"],
                    self.track["title"],
                )

    def test_metadata_write_failure_is_logged_without_breaking_extraction(self):
        with (
            patch.object(YouTube.os, "replace", side_effect=OSError("disk full")),
            patch.object(YouTube, "warn") as warn,
        ):
            YouTube.cache_youtube_info(self.url, self.url, self.track)
            warn.assert_called_once()
        self.assertEqual(list(Path("cache").glob("*.tmp")), [])
        self.assertFalse(Path(self.info_path).exists())

    def test_cache_download_is_skipped_when_audio_exists(self):
        Path(self.audio_path).write_bytes(b"old audio")
        with patch.object(YouTube, "YoutubeDL") as factory:
            download_and_cache_youtube_track(self.url)
            YouTube.download_youtube_media_thread(self.url)
            factory.assert_not_called()

    def test_playlist_download_populates_metadata(self):
        with patch.object(YouTube, "YoutubeDL") as factory:
            ydl = factory.return_value.__enter__.return_value
            ydl.extract_info.return_value = self.track
            download_and_cache_youtube_track(self.url)
            ydl.extract_info.assert_called_once_with(self.url, download=True)
        self.assertEqual(
            YouTube.get_cached_youtube_info(self.url)["info"]["title"],
            self.track["title"],
        )

    def test_precache_hit_does_not_extract_or_download(self):
        self.seed_cache()
        with patch.object(YouTube, "YoutubeDL") as factory:
            self.assertFalse(YouTube.precache_youtube_track(self.url))
            factory.assert_not_called()

    def test_precache_downloads_audio_and_metadata_in_one_extraction(self):
        with patch.object(YouTube, "YoutubeDL") as factory:
            ydl = factory.return_value.__enter__.return_value

            def extract(url, download):
                self.assertTrue(download)
                Path(self.audio_path).write_bytes(b"downloaded")
                return self.track

            ydl.extract_info.side_effect = extract
            self.assertTrue(YouTube.precache_youtube_track(self.url))
            ydl.extract_info.assert_called_once_with(self.url, download=True)
        self.assertIsNotNone(YouTube.get_cached_youtube_source(self.url))

    def test_precache_backfills_metadata_without_downloading_existing_audio(self):
        Path(self.audio_path).write_bytes(b"old audio")
        with patch.object(YouTube, "YoutubeDL") as factory:
            ydl = factory.return_value.__enter__.return_value
            ydl.extract_info.return_value = self.track
            self.assertTrue(YouTube.precache_youtube_track(self.url))
            ydl.extract_info.assert_called_once_with(self.url, download=False)

    def test_precache_query_resolves_and_downloads_synchronously(self):
        with patch.object(YouTube, "YoutubeDL") as factory:
            ydl = factory.return_value.__enter__.return_value

            def extract(url, download):
                if download:
                    Path(self.audio_path).write_bytes(b"downloaded")
                    return self.track
                return {"entries": [self.track]}

            ydl.extract_info.side_effect = extract
            self.assertTrue(YouTube.precache_youtube_track("my song"))
            self.assertEqual(ydl.extract_info.call_count, 2)
            ydl.extract_info.assert_called_with(self.url, download=True)
        self.assertIsNotNone(YouTube.get_cached_youtube_source("my song"))

    def test_precache_fills_missing_audio_using_cached_query_resolution(self):
        YouTube.cache_youtube_info("my song", self.url, self.track)
        with patch.object(YouTube, "YoutubeDL") as factory:
            ydl = factory.return_value.__enter__.return_value

            def extract(url, download):
                Path(self.audio_path).write_bytes(b"downloaded")
                return self.track

            ydl.extract_info.side_effect = extract
            self.assertTrue(YouTube.precache_youtube_track("my song"))
            ydl.extract_info.assert_called_once_with(self.url, download=True)

    def test_concurrent_downloads_share_one_audio_extraction(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor

        entered = threading.Event()
        release = threading.Event()
        with patch.object(YouTube, "YoutubeDL") as factory:
            ydl = factory.return_value.__enter__.return_value

            def extract(url, download):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("Test download was not released")
                Path(self.audio_path).write_bytes(b"downloaded")
                return self.track

            ydl.extract_info.side_effect = extract
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(
                    YouTube.download_and_cache_youtube_media, self.url
                )
                self.assertTrue(entered.wait(5))
                second = executor.submit(
                    YouTube.download_and_cache_youtube_media, self.url
                )
                release.set()
                first.result(timeout=5)
                second.result(timeout=5)
            ydl.extract_info.assert_called_once_with(self.url, download=True)

    def test_precache_does_not_claim_success_if_audio_or_metadata_missing(self):
        for metadata in (self.track, {"id": self.track["id"]}):
            with (
                self.subTest(metadata=metadata),
                patch.object(YouTube, "YoutubeDL") as factory,
            ):
                factory.return_value.__enter__.return_value.extract_info.return_value = metadata
                with self.assertRaisesRegex(RuntimeError, "still missing"):
                    YouTube.precache_youtube_track(self.url)

    def test_export_resolves_downloaded_path_after_download(self):
        import asyncio
        from types import SimpleNamespace

        cog = MusicCog.__new__(MusicCog)
        interaction = SimpleNamespace(guild=SimpleNamespace(id=11, name="Test"))

        def download(url):
            Path(self.audio_path).write_bytes(b"downloaded")

        with patch(
            "hifisuperstar.cogs.Music.MusicCog.download_and_cache_youtube_track",
            side_effect=download,
        ):
            path = asyncio.run(
                cog._resolve_and_cache_track(
                    {"title": "Song", "url": self.url}, interaction
                )
            )
        self.assertEqual(path, self.audio_path)

    def test_export_of_cached_query_does_not_query_or_download(self):
        import asyncio
        from types import SimpleNamespace

        self.seed_cache("my song")
        cog = MusicCog.__new__(MusicCog)
        interaction = SimpleNamespace(guild=SimpleNamespace(id=11, name="Test"))
        with (
            patch("hifisuperstar.cogs.Music.MusicCog.YoutubeDL") as factory,
            patch(
                "hifisuperstar.cogs.Music.MusicCog.download_and_cache_youtube_track"
            ) as download,
        ):
            path = asyncio.run(
                cog._resolve_and_cache_track(
                    {"title": "Song", "url": "my song"}, interaction
                )
            )
            factory.assert_not_called()
            download.assert_not_called()
        self.assertEqual(path, self.audio_path)


if __name__ == "__main__":
    unittest.main()
