import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
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

    def titles_after_unplayable(self, unplayable, **options):
        self.player.options.update(options)

        def source(url, allowed_mime_types=None):
            if url in unplayable:
                raise RuntimeError("Private video")
            return {}, url, "audio"

        return patch("hifisuperstar.core.Music.Player.media_get_source", source)

    async def test_unplayable_track_is_skipped_instead_of_ending_the_queue(self):
        self.player.playlist.jump_to(1)  # "two" can not be loaded
        with (
            self.titles_after_unplayable({"two"}),
            patch.object(self.player, "play_track", return_value=True) as play,
        ):
            await self.player._resume_playback()
        self.assertEqual(self.player.playlist.get_current_track()["title"], "Three")
        self.assertFalse(self.player.stopped)
        play.assert_called_once()
        self.assertEqual(play.call_args.kwargs["media_source"][1], "three")

    async def test_queue_stops_when_no_track_is_playable(self):
        self.player.playlist.jump_to(0)
        with (
            self.titles_after_unplayable({"one", "two", "three"}),
            patch.object(self.player, "play_track") as play,
            patch.object(self.player, "stop_track", new=AsyncMock()) as stop,
        ):
            await self.player._resume_playback()
        play.assert_not_called()
        stop.assert_awaited_once()

    async def test_unplayable_tracks_do_not_loop_forever_with_repeat_all(self):
        self.player.playlist.jump_to(0)
        with (
            self.titles_after_unplayable({"one", "two", "three"}, repeat_all=True),
            patch.object(self.player, "stop_track", new=AsyncMock()) as stop,
        ):
            await asyncio.wait_for(self.player._resume_playback(), timeout=2)
        stop.assert_awaited_once()

    async def finish_track(self):
        with patch.object(self.player, "_resume_playback", new=AsyncMock()):
            self.player._after_track(None, self.player._playback_id)
            await asyncio.sleep(0)

    async def test_skip_moves_on_even_when_repeat_is_on(self):
        self.player.options["repeat"] = True
        self.player.skip_track()
        await self.finish_track()
        self.assertEqual(self.player.playlist.get_current_track()["title"], "Two")

    async def test_prev_goes_back_even_when_repeat_is_on(self):
        self.player.playlist.jump_to(1)
        self.player.options["repeat"] = True
        self.player.prev_track()
        await self.finish_track()
        self.assertEqual(self.player.playlist.get_current_track()["title"], "One")

    async def test_repeat_still_replays_when_the_track_ends_by_itself(self):
        self.player.options["repeat"] = True
        await self.finish_track()
        self.assertEqual(self.player.playlist.get_current_track()["title"], "One")

    async def test_prev_with_repeat_does_not_reverse_playback_later(self):
        self.player.playlist.jump_to(1)
        self.player.options["repeat"] = True
        self.player.prev_track()
        await self.finish_track()
        self.player.options["repeat"] = False
        await self.finish_track()
        self.assertEqual(self.player.playlist.get_current_track()["title"], "Two")

    async def test_starting_a_track_clears_pending_skip_requests(self):
        self.player.prev = True
        self.player._advance_requested = True
        with (
            patch("hifisuperstar.core.Music.Player.discord.FFmpegPCMAudio"),
            patch("hifisuperstar.core.Music.Player.discord.PCMVolumeTransformer"),
        ):
            self.player.play_track(media_source=({}, "one", "audio"))
        self.assertFalse(self.player.prev)
        self.assertFalse(self.player._advance_requested)

    async def test_reconnect_resume_does_not_count_a_new_play(self):
        with (
            patch("hifisuperstar.core.Music.Player.media_get_source") as source,
            patch("hifisuperstar.core.Music.Player.discord.FFmpegPCMAudio"),
            patch("hifisuperstar.core.Music.Player.discord.PCMVolumeTransformer"),
        ):
            source.return_value = ({}, "one", "audio")
            self.player.interaction.guild.voice_client.source = None
            await self.player._resume_if_idle(self.voice)
        self.player.play_counter.count_playback.assert_not_called()

    def test_a_fresh_track_counts_a_play(self):
        with (
            patch("hifisuperstar.core.Music.Player.discord.FFmpegPCMAudio"),
            patch("hifisuperstar.core.Music.Player.discord.PCMVolumeTransformer"),
            patch.object(self.player, "_start_voice_monitor"),
        ):
            self.player.play_track(media_source=({}, "one", "audio"))
            self.player.play_counter.count_playback.assert_called_once()
            self.player.play_track(media_source=({}, "one", "audio"), count=False)
            self.player.play_counter.count_playback.assert_called_once()

    async def test_queueing_a_track_while_the_radio_plays_switches_to_the_track(self):
        self.player.streaming = True
        self.player._stream_url = "radio"
        self.voice.is_playing.side_effect = [True, False, False]
        playback_id = self.player._playback_id
        with (
            patch(
                "hifisuperstar.core.Music.Player.media_get_source",
                return_value=({"info": {"title": "Song"}}, "song", "audio"),
            ),
            patch.object(self.player, "play_track", return_value=True) as play,
        ):
            self.player.playlist.clear()
            result = await self.player.queue_track("song")
        self.assertTrue(result)
        self.voice.stop.assert_called_once()
        self.assertGreater(self.player._playback_id, playback_id)  # old callback is stale
        self.assertFalse(self.player.streaming)
        play.assert_called_once()

    async def test_mode_reminder_lists_every_active_mode(self):
        self.assertEqual(self.player.mode_reminder(), "")
        self.player.options["repeat"] = True
        self.assertIn("/repeat", self.player.mode_reminder())
        self.player.set_shuffle(True)
        self.player.options["repeat_all"] = True
        reminder = self.player.mode_reminder()
        for command in ("/repeat.", "/repeat_all)", "/shuffle)"):
            self.assertIn(command, reminder)
        self.assertTrue(all(line.startswith("-# ") for line in reminder.splitlines()))

    async def test_music_commands_remind_about_active_modes(self):
        from hifisuperstar.cogs.Music.MusicCog import MusicCog

        cog = MusicCog.__new__(MusicCog)
        cog.get_player = AsyncMock(return_value=self.player)
        interaction = SimpleNamespace(guild=self.voice.channel.guild)
        respond = AsyncMock()
        patches = (
            patch("hifisuperstar.cogs.Music.MusicCog.check_server", new=AsyncMock(return_value=True)),
            patch("hifisuperstar.cogs.Music.MusicCog.Acl.check_and_fail", new=AsyncMock(return_value=True)),
            patch("hifisuperstar.cogs.Music.MusicCog.respond", respond),
            patch.object(self.player, "skip_track", return_value=True),
            patch.object(cog, "_require_same_channel", new=AsyncMock(return_value=True)),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        await MusicCog.skip.callback(cog, interaction)
        self.assertEqual(respond.await_args.args[1], "Done!")

        self.player.options["shuffle"] = True
        await MusicCog.skip.callback(cog, interaction)
        self.assertIn("Done!", respond.await_args.args[1])
        self.assertIn("/shuffle", respond.await_args.args[1])

    async def test_llm_music_tools_include_the_reminder(self):
        from hifisuperstar.cogs.LLM.Tools.MusicTool import create_music_tools

        music = SimpleNamespace(players={"11": self.player}, config={})
        message = SimpleNamespace(
            guild=SimpleNamespace(id=11), author=SimpleNamespace(id=1)
        )
        tools = {t.name: t for t in create_music_tools(music, message)}
        with patch.object(self.player, "skip_track", return_value=True):
            self.assertNotIn("-#", tools["music_skip"].invoke({}))
            self.player.options["repeat"] = True
            self.assertIn("Repeat is on", tools["music_skip"].invoke({}))
        self.assertIn("Repeat is on", tools["music_get_queue"].invoke({}))

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

    def test_llm_reply_gets_the_reminder_once(self):
        from hifisuperstar.cogs.LLM.LLMCog import _with_mode_reminder

        player = MagicMock()
        player.mode_reminder.return_value = "-# 🔀 Shuffle is on"
        music = SimpleNamespace(players={"11": player})
        reply = _with_mode_reminder("Queued it!", music, 11)
        self.assertEqual(reply, "Queued it!\n-# 🔀 Shuffle is on")
        self.assertEqual(_with_mode_reminder(reply, music, 11), reply)
        self.assertEqual(_with_mode_reminder("Hi", music, 22), "Hi")
        self.assertEqual(_with_mode_reminder("Hi", None, 11), "Hi")

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


class FailureReasonTests(unittest.IsolatedAsyncioTestCase):
    def test_youtube_errors_are_explained(self):
        from hifisuperstar.core.Music.MediaErrors import describe_media_error

        cases = {
            "ERROR: [youtube] x: Sign in to confirm your age. This video may be inappropriate for some users.": "18+",
            "ERROR: [youtube] x: Private video. Sign in if you've been granted access": "private",
            "ERROR: [youtube] x: The uploader has not made this video available in your country": "region",
            "ERROR: [youtube] x: Video unavailable. This video contains content from Y, who has blocked it on copyright grounds": "copyright",
            "ERROR: [youtube] x: Sign in to confirm you're not a bot": "cookies",
            "ERROR: [youtube] x: Video unavailable": "unavailable",
        }
        for message, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertIn(expected, describe_media_error(DownloadError(message)))
        self.assertIn("timed out", describe_media_error(TimeoutError()))
        self.assertEqual(
            describe_media_error(DownloadError("ERROR: [youtube] x: odd failure")),
            "odd failure",
        )

    def test_empty_search_raises_a_readable_error(self):
        from hifisuperstar.core.Music.MediaErrors import (
            MediaNotFoundError,
            describe_media_error,
        )

        with self.assertRaises(MediaNotFoundError) as raised:
            YouTube.first_search_entry({"entries": [None]}, "nothing here")
        self.assertIn("nothing here", describe_media_error(raised.exception))

    async def test_queue_track_records_why_it_failed(self):
        guild = SimpleNamespace(id=11, name="Test", voice_client=MagicMock())
        guild.voice_client.is_connected.return_value = True
        interaction = SimpleNamespace(guild=guild, client=SimpleNamespace())
        with patch("hifisuperstar.core.Music.Player.PlayCounter"):
            player = Player(interaction, {"MusicCog": {"Allowed_Mime_Types": []}})

        def blocked(query, allowed_mime_types=None):
            raise DownloadError("ERROR: [youtube] x: Private video. Sign in")

        with patch("hifisuperstar.core.Music.Player.media_get_source", blocked):
            self.assertFalse(await player.queue_track("song"))
        self.assertIn("private", player.last_error)

        from hifisuperstar.cogs.Music.MusicCog import format_queue_failure

        self.assertEqual(
            format_queue_failure("song", player),
            "ERROR: Failed to queue 'song': the video is private.",
        )
        self.assertEqual(
            format_queue_failure("song", SimpleNamespace(last_error=None)),
            "ERROR: Failed to queue 'song'",
        )


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


class PlaylistRegressionTests(TemporaryDirectoryCase):
    def test_track_ids_are_unique_even_when_the_generator_repeats(self):
        ids = iter(["same", "same", "same", "other"])
        playlist = Playlist(11, "Dupes")
        with patch(
            "hifisuperstar.core.Music.Playlist.str_rand_crc32", lambda: next(ids)
        ):
            playlist.add_track("A", "a")
            playlist.add_track("B", "b")
        self.assertEqual([t["id"] for t in playlist.tracks], ["same", "other"])

    def test_remove_track_by_id_keeps_the_current_track(self):
        playlist = Playlist(11, "Q")
        for name in "abc":
            playlist.add_track(name, name)
        playlist.jump_to(2)
        self.assertTrue(playlist.remove_track(playlist.tracks[0]["id"]))
        self.assertEqual(playlist.get_current_track()["title"], "c")
        self.assertFalse(playlist.remove_track("missing"))

    def test_failed_save_does_not_rename_the_live_queue(self):
        from hifisuperstar.cogs.Music.MusicCog import MusicCog

        existing = Playlist(11, "Existing")
        existing.add_track("X", "x")
        self.assertTrue(existing.save())
        live = Playlist(11)
        live.add_track("Live", "live")
        original_name = live.get_name()
        cog = MusicCog.__new__(MusicCog)
        cog.get_player = AsyncMock(
            return_value=SimpleNamespace(get_playlist=lambda: live)
        )
        interaction = SimpleNamespace(guild=SimpleNamespace(id=11, name="T"))
        respond = AsyncMock()
        with (
            patch(
                "hifisuperstar.cogs.Music.MusicCog.check_server",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "hifisuperstar.cogs.Music.MusicCog.Acl.check_and_fail",
                new=AsyncMock(return_value=True),
            ),
            patch("hifisuperstar.cogs.Music.MusicCog.respond", respond),
        ):
            asyncio.run(MusicCog.playlist_save.callback(cog, interaction, "Existing"))
        self.assertIn("ERROR", respond.await_args.args[1])
        self.assertEqual(live.get_name(), original_name)


class MusicHelpTests(TemporaryDirectoryCase):
    CONFIG: ClassVar[dict] = {
        "Bot": {"Enabled_Cogs": ["Music", "LLM", "Spotify"]},
        "MusicCog": {"S3": {"Enabled": True}},
    }

    @staticmethod
    def text(embed):
        return embed.description + "\n".join(f.name + f.value for f in embed.fields)

    def test_help_mentions_every_music_command(self):
        from hifisuperstar.cogs.Music.MusicCog import MusicCog, build_music_help_embed

        text = self.text(build_music_help_embed(self.CONFIG, 11))
        for command in MusicCog.__cog_app_commands__:
            self.assertIn(f"/{command.name}", text, command.name)

    def test_help_fits_the_discord_embed_limits(self):
        from hifisuperstar.cogs.Music.MusicCog import build_music_help_embed

        embed = build_music_help_embed(self.CONFIG, 11)
        self.assertLessEqual(len(embed), 6000)
        self.assertLessEqual(len(embed.fields), 25)
        self.assertTrue(all(len(f.value) <= 1024 for f in embed.fields))

    def test_help_adapts_to_the_server(self):
        from hifisuperstar.cogs.Music.MusicCog import build_music_help_embed

        minimal = self.text(
            build_music_help_embed({"Bot": {"Enabled_Cogs": ["Music"]}}, 11)
        )
        self.assertNotIn("playlist_downloads", minimal)
        self.assertNotIn("spotify", minimal)
        self.assertNotIn("talk to me", minimal)

        save_resource("llm", 11, {"enabled": True, "channel_id": 42})
        self.assertIn("<#42>", self.text(build_music_help_embed(self.CONFIG, 11)))

        save_resource("llm", 11, {"enabled": False, "channel_id": 42})
        self.assertIn("/toggle_llm", self.text(build_music_help_embed(self.CONFIG, 11)))
        self.assertIn("playlist_downloads", self.text(build_music_help_embed(self.CONFIG, 11)))

    def test_command_replies_privately(self):
        from hifisuperstar.cogs.Music.MusicCog import MusicCog

        cog = MusicCog.__new__(MusicCog)
        cog.config = self.CONFIG
        respond = AsyncMock()
        with (
            patch("hifisuperstar.cogs.Music.MusicCog.check_server", new=AsyncMock(return_value=True)),
            patch("hifisuperstar.cogs.Music.MusicCog.respond", respond),
        ):
            asyncio.run(
                MusicCog.music_help.callback(
                    cog, SimpleNamespace(guild=SimpleNamespace(id=11, name="T"))
                )
            )
        self.assertTrue(respond.await_args.kwargs["ephemeral"])


class EstablishDominanceTests(TemporaryDirectoryCase):
    @staticmethod
    def bot_member(name="DesktopMusicHelper", discriminator="3176", is_bot=True, guild_id=11):
        return SimpleNamespace(
            id=7,
            name=name,
            discriminator=discriminator,
            bot=is_bot,
            guild=SimpleNamespace(id=guild_id, name="T"),
            voice=SimpleNamespace(channel="Music"),
            move_to=AsyncMock(),
        )

    def make_cog(self, guilds=()):
        from hifisuperstar.cogs.EstablishDominance.EstablishDominanceCog import (
            EstablishDominanceCog,
        )

        cog = EstablishDominanceCog.__new__(EstablishDominanceCog)
        cog.config = {
            "EstablishDominanceCog": {
                "Blocked_Bots": [{"Name": "DesktopMusicHelper", "Discriminator": "3176"}]
            }
        }
        cog.bot = SimpleNamespace(guilds=list(guilds))
        cog.enabled_guilds = {}
        return cog

    def test_only_the_configured_bot_is_blocked(self):
        from hifisuperstar.cogs.EstablishDominance.EstablishDominanceCog import (
            is_blocked_bot,
        )

        rivals = [{"Name": "DesktopMusicHelper", "Discriminator": "3176"}]
        blocked = lambda member: is_blocked_bot(member, rivals)
        self.assertTrue(blocked(self.bot_member()))
        self.assertTrue(blocked(self.bot_member(name="desktopmusichelper")))
        self.assertTrue(blocked(self.bot_member(discriminator="0")))  # migrated username
        self.assertFalse(blocked(self.bot_member(discriminator="1234")))
        self.assertFalse(blocked(self.bot_member(name="Other Bot")))
        self.assertFalse(blocked(self.bot_member(is_bot=False)))  # a human with that name
        self.assertTrue(is_blocked_bot(self.bot_member(name="x"), [{"Id": "7"}]))

    def test_joining_voice_disconnects_the_bot(self):
        cog = self.make_cog()
        member = self.bot_member()
        joined = SimpleNamespace(channel="Music")
        asyncio.run(cog.on_voice_state_update(member, SimpleNamespace(channel=None), joined))
        member.move_to.assert_awaited_once()
        self.assertIsNone(member.move_to.await_args.args[0])

    def test_nobody_is_blocked_without_configuration(self):
        cog = self.make_cog()
        cog.config = {}
        member = self.bot_member()
        asyncio.run(cog.on_voice_state_update(member, SimpleNamespace(channel=None), SimpleNamespace(channel="Music")))
        member.move_to.assert_not_awaited()

    def test_leaving_muting_and_other_members_are_ignored(self):
        cog = self.make_cog()
        member = self.bot_member()
        asyncio.run(cog.on_voice_state_update(member, SimpleNamespace(channel="Music"), SimpleNamespace(channel=None)))
        asyncio.run(cog.on_voice_state_update(member, SimpleNamespace(channel="Music"), SimpleNamespace(channel="Music")))
        member.move_to.assert_not_awaited()
        other = self.bot_member(name="Someone", is_bot=False)
        asyncio.run(cog.on_voice_state_update(other, SimpleNamespace(channel=None), SimpleNamespace(channel="Music")))
        other.move_to.assert_not_awaited()

    def test_missing_permission_is_logged_not_raised(self):
        cog = self.make_cog()
        member = self.bot_member()
        member.move_to.side_effect = discord.Forbidden(MagicMock(status=403), "no")
        asyncio.run(cog.on_voice_state_update(member, SimpleNamespace(channel=None), SimpleNamespace(channel="Music")))

    def test_toggle_command_switches_it_off_and_on_per_guild(self):
        from hifisuperstar.cogs.EstablishDominance.EstablishDominanceCog import (
            EstablishDominanceCog,
        )

        lingering = self.bot_member()
        guild = SimpleNamespace(
            id=11,
            name="T",
            voice_channels=[SimpleNamespace(members=[lingering])],
        )
        cog = self.make_cog([guild])
        interaction = SimpleNamespace(guild=guild)
        respond = AsyncMock()

        def toggle():
            with (
                patch("hifisuperstar.cogs.EstablishDominance.EstablishDominanceCog.check_server", new=AsyncMock(return_value=True)),
                patch("hifisuperstar.cogs.EstablishDominance.EstablishDominanceCog.respond", respond),
            ):
                asyncio.run(EstablishDominanceCog.establish_dominance_toggle.callback(cog, interaction))

        self.assertTrue(cog.is_enabled(11))
        toggle()  # off
        self.assertFalse(cog.is_enabled(11))
        self.assertIn("Standing down", respond.await_args.args[1])
        lingering.move_to.assert_not_awaited()

        join = SimpleNamespace(channel="Music")
        asyncio.run(cog.on_voice_state_update(lingering, SimpleNamespace(channel=None), join))
        lingering.move_to.assert_not_awaited()  # disabled: nothing happens

        # The choice survives a restart and does not leak into other servers
        self.assertFalse(self.make_cog().is_enabled(11))
        self.assertTrue(self.make_cog().is_enabled(22))

        toggle()  # on again: bots that are already in voice are removed right away
        self.assertTrue(cog.is_enabled(11))
        lingering.move_to.assert_awaited_once()

    def test_startup_scan_removes_bots_that_were_already_in_voice(self):
        lingering = self.bot_member()
        guild = SimpleNamespace(id=11, name="T", voice_channels=[SimpleNamespace(members=[lingering])])
        cog = self.make_cog([guild])
        asyncio.run(cog.on_ready())
        lingering.move_to.assert_awaited_once()


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
