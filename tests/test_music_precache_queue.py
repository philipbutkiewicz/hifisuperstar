import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from hifisuperstar.cogs.Music.MusicCog import MusicCog
from hifisuperstar.core.Acl import Rule
from hifisuperstar.core.Music.Playlist import Playlist


class MusicPrecacheQueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cog = MusicCog({})
        self.playlist = Playlist(11)
        self.player = SimpleNamespace(get_playlist=lambda: self.playlist)
        self.message = SimpleNamespace(edit=AsyncMock())
        self.response_message = SimpleNamespace(id=123)
        self.interaction = SimpleNamespace(
            guild=SimpleNamespace(id=11, name="Test"),
            original_response=AsyncMock(return_value=self.response_message),
            response=SimpleNamespace(is_done=lambda: False, send_message=AsyncMock()),
            followup=SimpleNamespace(
                send=AsyncMock(return_value=self.response_message)
            ),
            channel=SimpleNamespace(fetch_message=AsyncMock(return_value=self.message)),
        )
        for target, value in (
            ("check_server", AsyncMock(return_value=True)),
            ("Acl.check_and_fail", AsyncMock(return_value=True)),
            ("respond", AsyncMock()),
        ):
            mock = patch(f"hifisuperstar.cogs.Music.MusicCog.{target}", new=value)
            mock.start()
            self.addCleanup(mock.stop)
            if target == "respond":
                self.respond = value
            elif target == "Acl.check_and_fail":
                self.acl = value
            else:
                self.check_server = value
        player = patch.object(
            self.cog, "get_player", new=AsyncMock(return_value=self.player)
        )
        player.start()
        self.addCleanup(player.stop)

    async def run_command(self):
        await MusicCog.music_precache_queue.callback(self.cog, self.interaction)

    async def test_entire_queue_is_snapshotted_and_failures_do_not_abort(self):
        for title, url in (
            ("Earlier", "https://youtube.com/watch?v=earlier"),
            ("Current", "already"),
            ("Failed", "broken"),
            ("Direct", "https://example.com/audio.mp3"),
            ("Missing", None),
            ("Last", "last"),
        ):
            self.playlist.add_track(title, url)
        self.playlist.jump_to(1)
        original = [dict(track) for track in self.playlist.get_tracks()]
        calls = []

        def precache(query):
            calls.append(query)
            if query == "broken":
                raise OSError("offline")
            return query != "already"

        with patch(
            "hifisuperstar.cogs.Music.MusicCog.precache_youtube_track",
            side_effect=precache,
        ):
            await self.run_command()
        self.assertEqual(calls, [original[0]["url"], "already", "broken", "last"])
        self.assertEqual(self.playlist.get_tracks(), original)
        self.assertEqual(self.playlist.get_current_track_index(), 1)
        self.acl.assert_awaited_once_with(Rule.MUSIC_PRECACHE_QUEUE, self.interaction)
        summary = self.message.edit.await_args.kwargs["content"]
        self.assertIn("2 cached, 1 already cached", summary)
        self.assertIn("1 non-YouTube tracks skipped, 2 failed (6 total)", summary)
        self.assertFalse(self.cog.queue_precaches_in_progress)
        self.assertGreater(self.message.edit.await_count, 1)

    async def test_empty_queue_does_not_start_work(self):
        with patch(
            "hifisuperstar.cogs.Music.MusicCog.precache_youtube_track"
        ) as precache:
            await self.run_command()
            precache.assert_not_called()
        self.assertIn("empty", self.respond.await_args.args[1])

    async def test_permission_denial_does_not_start_work(self):
        self.acl.return_value = False
        await self.run_command()
        self.cog.get_player.assert_not_awaited()
        self.respond.assert_not_awaited()

    async def test_dm_does_not_access_guild(self):
        self.check_server.return_value = False
        self.interaction.guild = None
        await self.run_command()
        self.acl.assert_not_awaited()

    async def test_duplicate_guild_run_is_rejected(self):
        self.cog.queue_precaches_in_progress.add("11")
        await self.run_command()
        self.cog.get_player.assert_not_awaited()
        self.assertIn("already running", self.respond.await_args.args[1])
        self.assertEqual(self.cog.queue_precaches_in_progress, {"11"})

    async def test_another_guild_is_not_blocked(self):
        self.cog.queue_precaches_in_progress.add("22")
        self.playlist.add_track("First", "first")
        with patch(
            "hifisuperstar.cogs.Music.MusicCog.precache_youtube_track",
            return_value=False,
        ) as precache:
            await self.run_command()
            precache.assert_called_once_with("first")
        self.assertEqual(self.cog.queue_precaches_in_progress, {"22"})

    async def test_progress_failure_is_logged_and_caching_continues(self):
        self.playlist.add_track("First", "first")
        self.playlist.add_track("Second", "second")
        self.message.edit.side_effect = [
            discord.HTTPException(
                SimpleNamespace(status=500, reason="Error"), "failed"
            ),
            None,
        ]
        with (
            patch(
                "hifisuperstar.cogs.Music.MusicCog.precache_youtube_track",
                return_value=True,
            ) as precache,
            patch("hifisuperstar.cogs.Music.MusicCog.warn") as warn,
        ):
            await self.run_command()
            self.assertEqual(precache.call_count, 2)
            warn.assert_called_once()
        self.assertIn("2 cached", self.message.edit.await_args.kwargs["content"])
        self.assertFalse(self.cog.queue_precaches_in_progress)

    async def test_long_track_updates_progress_before_download_completes(self):
        self.playlist.add_track("Long track", "first")
        started = asyncio.Event()
        release = asyncio.Event()
        refreshed = asyncio.Event()
        real_wait_for = asyncio.wait_for

        async def worker(*args):
            started.set()
            await release.wait()
            return True

        waits = 0

        async def wait_for(awaitable, timeout):
            nonlocal waits
            waits += 1
            if waits == 1:
                await started.wait()
                awaitable.close()
                raise TimeoutError
            return await real_wait_for(awaitable, timeout)

        async def edit(**kwargs):
            if self.message.edit.await_count == 2:
                refreshed.set()

        self.message.edit.side_effect = edit
        with (
            patch(
                "hifisuperstar.cogs.Music.MusicCog.asyncio.to_thread",
                side_effect=worker,
            ),
            patch(
                "hifisuperstar.cogs.Music.MusicCog.asyncio.wait_for",
                side_effect=wait_for,
            ),
        ):
            task = asyncio.create_task(self.run_command())
            await real_wait_for(refreshed.wait(), timeout=2)
            self.assertFalse(task.done())
            status = self.message.edit.await_args.kwargs["content"]
            self.assertIn("0/1", status)
            self.assertIn("Long track", status)
            release.set()
            await task
        self.assertIn("1 cached", self.message.edit.await_args.kwargs["content"])
        self.interaction.channel.fetch_message.assert_awaited_once_with(123)

    async def test_acknowledged_interaction_edits_the_followup_message(self):
        self.playlist.add_track("First", "first")
        self.interaction.response.is_done = lambda: True
        self.interaction.followup.send.return_value = SimpleNamespace(id=456)
        with patch(
            "hifisuperstar.cogs.Music.MusicCog.precache_youtube_track",
            return_value=False,
        ):
            await self.run_command()
        self.interaction.followup.send.assert_awaited_once()
        self.assertTrue(self.interaction.followup.send.await_args.kwargs["wait"])
        self.interaction.original_response.assert_not_awaited()
        self.interaction.channel.fetch_message.assert_awaited_once_with(456)

    async def test_queue_edits_during_precache_are_not_included(self):
        self.playlist.add_track("First", "first")
        self.playlist.add_track("Second", "second")
        queries = []

        def precache(query):
            queries.append(query)
            if query == "first":
                self.playlist.clear()
                self.playlist.add_track("Added", "added")
            return True

        with patch(
            "hifisuperstar.cogs.Music.MusicCog.precache_youtube_track",
            side_effect=precache,
        ):
            await self.run_command()
        self.assertEqual(queries, ["first", "second"])
        self.assertEqual(self.playlist.get_tracks()[0]["url"], "added")

    async def test_cancellation_releases_guild_guard(self):
        self.playlist.add_track("First", "first")
        started = asyncio.Event()

        async def worker(*args):
            started.set()
            await asyncio.Event().wait()

        with patch(
            "hifisuperstar.cogs.Music.MusicCog.asyncio.to_thread", side_effect=worker
        ):
            task = asyncio.create_task(self.run_command())
            await started.wait()
            self.assertIn("11", self.cog.queue_precaches_in_progress)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertFalse(self.cog.queue_precaches_in_progress)


if __name__ == "__main__":
    unittest.main()
