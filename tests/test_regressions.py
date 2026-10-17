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

    async def test_shuffle_plays_every_track_once_then_stops(self):
        self.assertTrue(self.player.set_shuffle())
        seen = [self.player.playlist.get_current_track()["id"]]
        with (
            patch.object(self.player, "_resume_playback", new=AsyncMock()),
            patch.object(self.player, "stop_track", new=AsyncMock()) as stop,
        ):
            for _ in range(2):
                self.player._after_track(None, self.player._playback_id)
                await asyncio.sleep(0)
                seen.append(self.player.playlist.get_current_track()["id"])
            self.assertEqual(len(set(seen)), 3)
            self.player._after_track(None, self.player._playback_id)
            await asyncio.sleep(0.05)
            stop.assert_awaited_once()

    async def test_shuffle_repeat_all_starts_a_new_round(self):
        self.player.set_shuffle()
        self.player.options["repeat_all"] = True
        with (
            patch.object(self.player, "_resume_playback", new=AsyncMock()),
            patch.object(self.player, "stop_track", new=AsyncMock()) as stop,
        ):
            for _ in range(10):
                self.player._after_track(None, self.player._playback_id)
                await asyncio.sleep(0)
                self.assertIsNotNone(self.player.playlist.get_current_track())
            stop.assert_not_awaited()

    async def test_shuffle_prev_returns_to_the_track_that_played_before(self):
        self.player.set_shuffle()
        first = self.player.playlist.get_current_track()["id"]
        with patch.object(self.player, "_resume_playback", new=AsyncMock()):
            self.player._after_track(None, self.player._playback_id)
            await asyncio.sleep(0)
            self.assertNotEqual(self.player.playlist.get_current_track()["id"], first)
            self.player.prev = True
            self.player._after_track(None, self.player._playback_id)
            await asyncio.sleep(0)
        self.assertEqual(self.player.playlist.get_current_track()["id"], first)

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


class LLMTests(TemporaryDirectoryCase):
    def test_name_mentions_are_resolved_to_user_ids(self):
        from hifisuperstar.cogs.LLM.LLMCog import _fix_mentions

        guild = SimpleNamespace(
            members=[SimpleNamespace(id=42, display_name="bagno", name="bagnz0r")]
        )
        self.assertEqual(
            _fix_mentions(guild, "hi <@bagno> and <@BAGNZ0R> and <@999> and <@ghost>"),
            "hi <@42> and <@42> and <@999> and @ghost",
        )

    def test_music_play_many_returns_before_the_tracks_are_queued(self):
        import hifisuperstar.cogs.LLM.Tools.MusicTool as music_tool

        async def run():
            gate = asyncio.Event()
            calls = []

            async def slow_queue(query):
                await gate.wait()
                calls.append(query)
                return {"title": query} if query != "b" else False

            player = MagicMock(stop_count=0)
            player.queue_track = slow_queue
            music = SimpleNamespace(players={"11": player}, config={})
            channel = SimpleNamespace(send=AsyncMock())
            message = SimpleNamespace(
                guild=SimpleNamespace(id=11, name="Test"),
                author=SimpleNamespace(id=1),
                channel=channel,
            )
            tools = {t.name: t for t in music_tool.create_music_tools(music, message)}
            join = patch.object(
                music_tool, "_join_voice", new=AsyncMock(return_value=True)
            )
            join.start()
            self.addCleanup(join.stop)
            result = await tools["music_play_many"].ainvoke({"queries": ["a", "b", "c"]})
            self.assertIn("Started queueing 3", result)
            self.assertEqual(calls, [])  # nothing finished yet, yet we already answered
            gate.set()
            await asyncio.gather(*music_tool._background_tasks)
            self.assertEqual(calls, ["a", "b", "c"])
            self.assertIn("b", channel.send.await_args.args[0])

            # A stop while the batch runs aborts the remaining songs
            calls.clear()
            player.stop_count = 0

            async def stopping_queue(query):
                calls.append(query)
                player.stop_count += 1
                return {"title": query}

            player.queue_track = stopping_queue
            await tools["music_play_many"].ainvoke({"queries": ["x", "y"]})
            await asyncio.gather(*music_tool._background_tasks)
            self.assertEqual(calls, ["x"])

        asyncio.run(run())


class ReimportTests(TemporaryDirectoryCase):
    def make_player(self):
        guild = SimpleNamespace(id=11, name="Test", voice_client=None)
        interaction = SimpleNamespace(guild=guild, client=SimpleNamespace())
        with patch("hifisuperstar.core.Music.Player.PlayCounter"):
            return Player(interaction, {"MusicCog": {"Allowed_Mime_Types": []}})

    def test_reimport_refreshes_the_cached_playlist(self):
        url = "https://www.youtube.com/playlist?list=PL123"
        one = [{"id": "a", "title": "A"}]
        two = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]

        def run(entries, **kwargs):
            with patch(
                "hifisuperstar.core.Music.Player.media_get_playlist",
                return_value=entries,
            ) as fetch:
                tracks = asyncio.run(self.make_player().queue_playlist(url, **kwargs))
            return tracks, fetch

        tracks, _ = run(one)
        self.assertEqual(len(tracks), 1)

        # Without the flag the cached copy wins and YouTube is not asked again
        tracks, fetch = run(two)
        self.assertEqual(len(tracks), 1)
        fetch.assert_not_called()

        tracks, fetch = run(two, reimport=True)
        fetch.assert_called_once()
        self.assertEqual(len(tracks), 2)

        # The refreshed copy is what gets cached from now on
        tracks, fetch = run(one)
        self.assertEqual(len(tracks), 2)
        fetch.assert_not_called()

    def test_failed_reimport_keeps_the_cached_copy(self):
        url = "https://www.youtube.com/playlist?list=PL123"
        with patch(
            "hifisuperstar.core.Music.Player.media_get_playlist",
            return_value=[{"id": "a", "title": "A"}],
        ):
            asyncio.run(self.make_player().queue_playlist(url))
        with patch(
            "hifisuperstar.core.Music.Player.media_get_playlist", return_value=None
        ):
            self.assertIsNone(
                asyncio.run(self.make_player().queue_playlist(url, reimport=True))
            )
        with patch("hifisuperstar.core.Music.Player.media_get_playlist") as fetch:
            tracks = asyncio.run(self.make_player().queue_playlist(url))
        self.assertEqual(len(tracks), 1)
        fetch.assert_not_called()


class VolumeTests(TemporaryDirectoryCase):
    def make_player(self, guild_id=11):
        guild = SimpleNamespace(id=guild_id, name="Test", voice_client=None)
        interaction = SimpleNamespace(guild=guild, client=SimpleNamespace())
        with patch("hifisuperstar.core.Music.Player.PlayCounter"):
            return Player(interaction, {"MusicCog": {"Allowed_Mime_Types": []}})

    def test_volume_survives_a_restart_and_is_per_guild(self):
        self.assertEqual(self.make_player().options["volume"], 0.02)
        player = self.make_player()
        self.assertTrue(player.set_volume(0.35))  # also works while nothing is playing
        self.assertEqual(self.make_player().options["volume"], 0.35)
        self.assertEqual(self.make_player(22).options["volume"], 0.02)

    def test_invalid_saved_volume_falls_back_to_the_default(self):
        save_resource("music", 11, {"volume": "loud"})
        self.assertEqual(self.make_player().options["volume"], 0.02)
        save_resource("music", 11, {"volume": 7})
        self.assertEqual(self.make_player().options["volume"], 1.0)

    def test_volume_applies_to_the_playing_source(self):
        player = self.make_player()
        source = SimpleNamespace(volume=0.02)
        player.interaction.guild.voice_client = SimpleNamespace(source=source)
        player.set_volume(0.5)
        self.assertEqual(source.volume, 0.5)


class WebTests(unittest.TestCase):
    def test_get_does_not_create_directories_and_base_path_is_absolute(self):
        from flask import Flask

        from web.config import ProdConfig
        from web.controllers.PlaylistController import PlaylistController

        with tempfile.TemporaryDirectory() as directory:
            app = Flask(__name__, template_folder=os.path.abspath("web/templates"))
            app.config["BASE_APP_PATH"] = directory
            with app.test_request_context():
                PlaylistController().list("12345")
            self.assertFalse(os.path.exists(os.path.join(directory, "storage")))
        self.assertTrue(os.path.isabs(ProdConfig.BASE_APP_PATH))


if __name__ == "__main__":
    unittest.main()
