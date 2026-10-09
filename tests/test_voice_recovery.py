import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from hifisuperstar.core.Music.Player import Player
from hifisuperstar.core.Server.Server import connect_voice, join_voice


class VoiceRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        media = patch(
            "hifisuperstar.core.Music.Player.media_get_source",
            return_value=({}, "resolved", "audio"),
        )
        media.start()
        self.addCleanup(media.stop)
        self.voice = MagicMock()
        self.voice.is_connected.return_value = True
        self.voice.is_playing.return_value = False
        self.voice.is_paused.return_value = False
        self.voice.disconnect = AsyncMock()
        self.guild = SimpleNamespace(id=11, name="Test", voice_client=self.voice)
        self.channel = SimpleNamespace(guild=self.guild, connect=AsyncMock())
        self.voice.channel = self.channel
        self.interaction = SimpleNamespace(
            guild=self.guild,
            user=SimpleNamespace(voice=SimpleNamespace(channel=self.channel)),
            client=SimpleNamespace(
                loop=asyncio.get_running_loop(), change_presence=AsyncMock()
            ),
        )
        with patch("hifisuperstar.core.Music.Player.PlayCounter"):
            self.player = Player(
                self.interaction,
                {"MusicCog": {"Allowed_Mime_Types": [], "Radio_URL": "radio"}},
            )
        self.player.playlist.add_track("First", "first")
        self.player.playlist.add_track("Second", "second")
        self.player.stopped = False
        self.player._voice_channel = self.channel

    async def test_join_replaces_disconnected_voice_client(self):
        self.voice.is_connected.return_value = False
        connected = MagicMock()
        self.channel.connect.return_value = connected
        self.assertIs(await connect_voice(self.channel), connected)
        self.voice.disconnect.assert_awaited_once_with(force=True)
        self.channel.connect.assert_awaited_once_with(timeout=30, reconnect=True)
        self.voice.move_to.assert_not_called()

    async def test_join_does_not_move_when_already_in_channel(self):
        self.assertIs(await connect_voice(self.channel), self.voice)
        self.voice.move_to.assert_not_called()
        self.channel.connect.assert_not_awaited()

    async def test_join_failure_is_reported(self):
        self.guild.voice_client = None
        self.channel.connect.side_effect = TimeoutError()
        with patch(
            "hifisuperstar.core.Server.Server.respond", new_callable=AsyncMock
        ) as respond:
            self.assertFalse(await join_voice(self.interaction))
            respond.assert_awaited_once()

    async def test_disconnected_callback_preserves_current_track(self):
        self.voice.is_connected.return_value = False
        with patch.object(self.player, "_start_voice_monitor") as monitor:
            self.player.after_track(None)
            await asyncio.sleep(0)
            self.assertEqual(self.player.playlist.get_current_track_index(), 0)
            self.assertTrue(self.player._restart_audio)
            monitor.assert_called_once()

    async def test_normal_completion_advances_and_stale_callbacks_do_not(self):
        with patch.object(self.player, "play_track") as play:
            self.player._after_track(None, -1)
            play.assert_not_called()
            self.player.after_track(None)
            await asyncio.sleep(0)
            await self.player._next_track_task
            self.assertEqual(self.player.playlist.get_current_track_index(), 1)
            play.assert_called_once_with(None, media_source=({}, "resolved", "audio"))

    async def test_recovery_reconnects_and_restarts_same_track_or_radio(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                self.player.stopped = False
                self.player.streaming = streaming
                self.player._stream_url = "radio" if streaming else None
                self.guild.voice_client = self.voice
                self.voice.is_connected.return_value = False
                connected = MagicMock()
                connected.is_connected.return_value = True
                connected.is_playing.return_value = False
                connected.is_paused.return_value = False

                async def reconnect(channel, recovered_voice=connected):
                    self.guild.voice_client = recovered_voice
                    return recovered_voice

                def resume(*args, **kwargs):
                    self.player.stopped = True

                with (
                    patch(
                        "hifisuperstar.core.Music.Player.asyncio.sleep",
                        new_callable=AsyncMock,
                    ),
                    patch(
                        "hifisuperstar.core.Music.Player.connect_voice",
                        new=AsyncMock(side_effect=reconnect),
                    ) as connect,
                    patch.object(self.player, "play_track", side_effect=resume) as play,
                ):
                    await self.player._monitor_voice()
                    connect.assert_awaited_once_with(self.channel)
                    play.assert_called_once_with(
                        "radio" if streaming else None,
                        media_source=None if streaming else ({}, "resolved", "audio"),
                    )
                    self.assertEqual(self.player.playlist.get_current_track_index(), 0)
                    self.assertFalse(self.player._recovering)

    async def test_library_reconnect_preserves_live_audio(self):
        self.voice.is_connected.return_value = False
        self.voice.is_playing.return_value = True
        sleeps = 0

        async def tick(delay):
            nonlocal sleeps
            sleeps += 1
            if sleeps == 2:
                self.voice.is_connected.return_value = True
            if sleeps == 3:
                self.player.stopped = True

        with (
            patch("hifisuperstar.core.Music.Player.asyncio.sleep", side_effect=tick),
            patch(
                "hifisuperstar.core.Music.Player.connect_voice", new_callable=AsyncMock
            ) as connect,
            patch.object(self.player, "play_track") as play,
        ):
            await self.player._monitor_voice()
            connect.assert_not_awaited()
            play.assert_not_called()

    async def test_fast_reconnect_restarts_audio_after_disconnected_callback(self):
        self.player._restart_audio = True

        def resume(*args, **kwargs):
            self.player.stopped = True

        with (
            patch(
                "hifisuperstar.core.Music.Player.asyncio.sleep", new_callable=AsyncMock
            ),
            patch.object(self.player, "play_track", side_effect=resume) as play,
        ):
            await self.player._monitor_voice()
            play.assert_called_once_with(None, media_source=({}, "resolved", "audio"))

    async def test_retry_exhaustion_resets_state_without_clearing_queue(self):
        self.voice.is_connected.return_value = False
        with (
            patch(
                "hifisuperstar.core.Music.Player.asyncio.sleep", new_callable=AsyncMock
            ),
            patch(
                "hifisuperstar.core.Music.Player.connect_voice",
                new=AsyncMock(side_effect=OSError("offline")),
            ) as connect,
        ):
            await self.player._monitor_voice()
            self.assertEqual(connect.await_count, 3)
            self.assertTrue(self.player.stopped)
            self.assertFalse(self.player._recovering)
            self.assertEqual(len(self.player.playlist.get_tracks()), 2)

    async def test_stop_cancels_monitor_and_ignores_late_callback(self):
        playback_id = self.player._playback_id
        self.player._start_voice_monitor()
        task = self.player._voice_task
        await asyncio.sleep(0)
        await self.player.stop_track()
        self.assertTrue(task.cancelled())
        self.assertTrue(self.player.stopped)
        self.voice.disconnect.assert_awaited_once_with(force=True)
        with patch.object(self.player, "play_track") as play:
            self.player._after_track(None, playback_id)
            play.assert_not_called()
        self.assertEqual(self.player.playlist.get_current_track_index(), 0)

    async def test_stop_handles_missing_voice_and_already_stopped_player(self):
        self.guild.voice_client = None
        await self.player.stop_track()
        await self.player.stop_track()
        self.assertTrue(self.player.stopped)
        self.assertIsNone(self.player._voice_task)

    async def test_connection_loss_at_voice_play_cleans_source_and_recovers(self):
        def fail(*args, **kwargs):
            self.voice.is_connected.return_value = False
            raise discord.ClientException("Not connected to voice.")

        self.voice.play.side_effect = fail
        with (
            patch("hifisuperstar.core.Music.Player.discord.FFmpegPCMAudio"),
            patch(
                "hifisuperstar.core.Music.Player.discord.PCMVolumeTransformer"
            ) as source,
            patch.object(self.player, "_start_voice_monitor") as monitor,
        ):
            self.assertFalse(self.player.play_track("radio"))
            source.return_value.cleanup.assert_called_once()
            monitor.assert_called_once()
            self.assertFalse(self.player.stopped)
            self.assertTrue(self.player._restart_audio)

    async def test_stop_during_media_lookup_prevents_late_playback(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def lookup(*args, **kwargs):
            entered.set()
            await release.wait()
            return ({}, "resolved", "audio")

        with (
            patch(
                "hifisuperstar.core.Music.Player.asyncio.to_thread", side_effect=lookup
            ),
            patch.object(self.player, "play_track") as play,
        ):
            task = asyncio.create_task(self.player._resume_playback())
            await entered.wait()
            await self.player.stop_track()
            release.set()
            await task
            play.assert_not_called()

    async def test_stop_cancels_inflight_reconnect(self):
        self.voice.is_connected.return_value = False
        entered = asyncio.Event()

        async def reconnect(channel):
            entered.set()
            await asyncio.Event().wait()

        with (
            patch(
                "hifisuperstar.core.Music.Player.asyncio.sleep", new_callable=AsyncMock
            ),
            patch(
                "hifisuperstar.core.Music.Player.connect_voice", side_effect=reconnect
            ),
        ):
            self.player._start_voice_monitor()
            task = self.player._voice_task
            await entered.wait()
            await self.player.stop_track()
            self.assertTrue(task.cancelled())
            self.assertFalse(self.player._recovering)

    async def test_skip_repeat_and_jump_behaviour_is_preserved(self):
        for repeat, jump, expected in (
            (False, -1, 1),
            (True, -1, 0),
            (False, 1, 1),
        ):
            with self.subTest(repeat=repeat, jump=jump):
                self.player.playlist.jump_to(0)
                self.player.options["repeat"] = repeat
                self.player.jump_to_index = jump
                with patch.object(
                    self.player, "_resume_playback", new_callable=AsyncMock
                ):
                    self.player.after_track(None)
                    await asyncio.sleep(0)
                    await self.player._next_track_task
                    self.assertEqual(
                        self.player.playlist.get_current_track_index(), expected
                    )


if __name__ == "__main__":
    unittest.main()
