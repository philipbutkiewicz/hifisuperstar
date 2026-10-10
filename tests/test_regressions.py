import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from yt_dlp.utils import DownloadError

from hifisuperstar.core.Acl.Acl import Acl, normalize_allowed
from hifisuperstar.core.Music import Media
from hifisuperstar.core.Music.MediaSourceProcessing import YouTube
from hifisuperstar.core.Music.MediaSourceProcessing.Direct import (
    MediaValidationError,
    media_check_url,
)
from hifisuperstar.core.Music.PlayCounter import PlayCounter
from hifisuperstar.core.Music.Player import Player
from hifisuperstar.core.Music.Playlist import Playlist
from hifisuperstar.io.Resources import load_resource, save_resource


class TemporaryDirectoryCase(unittest.TestCase):
    def setUp(self):
        self.previous_directory = os.getcwd()
        self.directory = tempfile.TemporaryDirectory()
        os.chdir(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(os.chdir, self.previous_directory)


class StorageTests(TemporaryDirectoryCase):
    def test_deleting_a_cached_playlist_that_is_not_indexed(self):
        playlist = Playlist(11, "yt-0x1")
        playlist.add_track("Song", "https://youtube.com/watch?v=a")
        self.assertTrue(playlist.save(cache=True))
        self.assertTrue(Playlist(11, "yt-0x1").delete())
        self.assertFalse(Playlist(11, "yt-0x1").load_from_storage())

    def test_corrupt_json_does_not_raise(self):
        save_resource("counts", 11, {"a": 1})
        with open("storage/counts.11.json", "w") as file:
            file.write("{not json")
        self.assertEqual(load_resource("counts", 11), {})
        playlist = Playlist(11, "Broken")
        os.makedirs(os.path.dirname(playlist.get_playlist_path()), exist_ok=True)
        with open(playlist.get_playlist_path(), "w") as file:
            file.write("{not json")
        self.assertFalse(playlist.load_from_storage())

    def test_resources_are_written_without_a_storage_directory(self):
        save_resource("acl", 5, {"x": True})
        self.assertEqual(load_resource("acl", 5), {"x": True})

    def test_play_counts_aggregate_by_url(self):
        counter = PlayCounter(11)
        for track_id in ("a", "b"):
            counter.count_playback({"id": track_id, "url": "u", "title": "T"})
        self.assertEqual(counter.get_all_counts()["u"]["count"], 2)


class AclTests(TemporaryDirectoryCase):
    def test_allowed_values_are_normalized(self):
        self.assertEqual(normalize_allowed("True"), "1")
        self.assertEqual(normalize_allowed("no"), "0")
        self.assertIsNone(normalize_allowed("maybe"))

    def test_admin_role_bypasses_admin_mode(self):
        acl = Acl(11)
        acl.toggle_admin_mode()
        respond = AsyncMock()

        def member(role_names):
            return SimpleNamespace(
                id=1, roles=[SimpleNamespace(name=name) for name in role_names]
            )

        with patch("hifisuperstar.core.Server.Server.respond", respond):
            admin = SimpleNamespace(user=member(["Admin"]), guild=None)
            other = SimpleNamespace(user=member(["DJ"]), guild=None)
            self.assertTrue(asyncio.run(acl.check_and_fail("MUSIC_PLAY", admin)))
            self.assertFalse(asyncio.run(acl.check_and_fail("MUSIC_PLAY", other)))


class YouTubeTests(unittest.TestCase):
    def test_permanent_errors_are_not_retried(self):
        ydl = Mock()
        ydl.extract_info.side_effect = DownloadError("Video unavailable")
        with (
            patch.object(YouTube.time, "sleep") as sleep,
            self.assertRaises(DownloadError),
        ):
            YouTube.extract_youtube_info(ydl, "https://youtube.com/watch?v=a")
        self.assertEqual(ydl.extract_info.call_count, 1)
        sleep.assert_not_called()

    def test_best_audio_url_tolerates_missing_fields(self):
        formats = [
            {"ext": "m4a"},
            {"resolution": "audio only", "ext": "m4a", "url": "u", "quality": None},
        ]
        self.assertEqual(YouTube.get_best_audio_url({"formats": formats}), "u")
        self.assertIsNone(YouTube.get_best_audio_url({}))


class MediaTests(unittest.TestCase):
    def test_youtube_domain_detection(self):
        self.assertTrue(Media.is_youtube_domain("https://music.youtube.com/watch?v=a"))
        self.assertTrue(Media.is_youtube_domain("https://m.youtube.com/watch?v=a"))
        self.assertFalse(Media.is_youtube_domain("https://evilyoutube.com/x"))
        self.assertFalse(Media.is_youtube_domain("https://youtube.com.evil.test/x"))

    def test_private_addresses_are_refused(self):
        for url in ("http://127.0.0.1/a.mp3", "http://169.254.169.254/latest"):
            with (
                self.subTest(url=url),
                patch(
                    "hifisuperstar.core.Music.MediaSourceProcessing.Direct.requests.get"
                ) as get,
                self.assertRaises(MediaValidationError),
            ):
                media_check_url(url, ["audio/mpeg"])
            get.assert_not_called()

    def test_content_type_parameters_are_ignored(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.is_redirect = False
        response.headers = {"Content-Type": "Audio/MPEG; charset=binary"}
        with (
            patch(
                "hifisuperstar.core.Music.MediaSourceProcessing.Direct._assert_public_host"
            ),
            patch(
                "hifisuperstar.core.Music.MediaSourceProcessing.Direct.requests.get",
                return_value=response,
            ) as get,
        ):
            media_check_url("https://example.com/a", ["audio/mpeg"])
        self.assertTrue(get.call_args.kwargs["stream"])


class PlayerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.voice = MagicMock()
        self.voice.is_connected.return_value = True
        self.voice.is_playing.return_value = False
        self.voice.is_paused.return_value = False
        guild = SimpleNamespace(id=11, name="Test", voice_client=self.voice)
        self.voice.channel = SimpleNamespace(guild=guild)
        interaction = SimpleNamespace(
            guild=guild,
            client=SimpleNamespace(
                loop=asyncio.get_running_loop(), change_presence=AsyncMock()
            ),
        )
        with patch("hifisuperstar.core.Music.Player.PlayCounter"):
            self.player = Player(
                interaction, {"MusicCog": {"Allowed_Mime_Types": []}}
            )
        for name in ("One", "Two", "Three"):
            self.player.playlist.add_track(name, name.lower())
        self.player.stopped = False

    async def test_prev_flag_is_cleared_after_going_back(self):
        self.player.playlist.jump_to(2)
        self.player.prev = True
        with patch.object(self.player, "_resume_playback", new=AsyncMock()):
            self.player._after_track(None, self.player._playback_id)
            await asyncio.sleep(0)
        self.assertEqual(self.player.playlist.get_current_track_index(), 1)
        self.assertFalse(self.player.prev)

    async def test_skip_clears_a_pending_prev(self):
        self.player.prev = True
        self.assertTrue(self.player.skip_track())
        self.assertFalse(self.player.prev)

    async def test_queue_track_does_not_block_the_event_loop(self):
        loop_thread = __import__("threading").get_ident()
        seen = []

        def fake_source(query, allowed_mime_types=None):
            seen.append(__import__("threading").get_ident())
            return {"info": {"title": "Song"}, "is_youtube": True}, query, "audio"

        with (
            patch("hifisuperstar.core.Music.Player.media_get_source", fake_source),
            patch.object(self.player, "play_track", return_value=True) as play,
        ):
            self.player.playlist.clear()
            result = await self.player.queue_track("song")
        self.assertEqual(result["title"], "Song")
        self.assertNotEqual(seen[0], loop_thread)
        play.assert_called_once()

    async def test_voice_monitor_start_from_a_worker_thread_uses_the_loop(self):
        self.player.stopped = True  # the monitor exits right away
        await asyncio.to_thread(self.player._start_voice_monitor)
        await asyncio.sleep(0.05)
        self.assertIsNotNone(self.player._voice_task)


class WebTests(unittest.TestCase):
    def test_get_does_not_create_directories_and_base_path_is_absolute(self):
        from web.config import ProdConfig
        from web.controllers.PlaylistController import PlaylistController
        from flask import Flask

        with tempfile.TemporaryDirectory() as directory:
            app = Flask(__name__, template_folder=os.path.abspath("web/templates"))
            app.config["BASE_APP_PATH"] = directory
            with app.test_request_context():
                PlaylistController().list("12345")
            self.assertFalse(os.path.exists(os.path.join(directory, "storage")))
        self.assertTrue(os.path.isabs(ProdConfig.BASE_APP_PATH))


if __name__ == "__main__":
    unittest.main()
