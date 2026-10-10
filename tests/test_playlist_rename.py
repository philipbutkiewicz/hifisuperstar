import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from hifisuperstar.cogs.Music.MusicCog import MusicCog
from hifisuperstar.core.Acl import Rule
from hifisuperstar.core.Music.Playlist import Playlist


class PlaylistRenameTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        previous_directory = os.getcwd()
        os.chdir(directory.name)
        self.addCleanup(os.chdir, previous_directory)
        Path("storage").mkdir()
        self.playlist = Playlist(11, "Favorites")
        self.playlist.add_track("First", "https://example.com/first")
        self.playlist.add_track("Second", "https://example.com/second")
        self.assertTrue(self.playlist.save())
        self.original = Path(self.playlist.get_playlist_path()).read_bytes()
        self.cog = MusicCog.__new__(MusicCog)
        self.cog.players = {}
        self.interaction = SimpleNamespace(
            guild=SimpleNamespace(id=11, name="Test"),
            user=SimpleNamespace(roles=[SimpleNamespace(name="Admin", id=123)]),
        )
        server = patch(
            "hifisuperstar.cogs.Music.MusicCog.check_server",
            new=AsyncMock(return_value=True),
        )
        self.server = server.start()
        self.addCleanup(server.stop)
        acl = patch(
            "hifisuperstar.cogs.Music.MusicCog.Acl.check_and_fail",
            new=AsyncMock(return_value=True),
        )
        self.acl = acl.start()
        self.addCleanup(acl.stop)
        respond = patch("hifisuperstar.cogs.Music.MusicCog.respond", new=AsyncMock())
        self.respond = respond.start()
        self.addCleanup(respond.stop)

    async def run_command(self, name="Favorites", new_name="Renamed"):
        await MusicCog.playlist_rename.callback(
            self.cog, self.interaction, name, new_name
        )

    def assert_original_preserved(self):
        self.assertEqual(
            Path(self.playlist.get_playlist_path()).read_bytes(), self.original
        )
        self.assertEqual(self.playlist.get_available_playlists(), ["Favorites"])
        self.assertFalse(Path(Playlist(11, "Renamed").get_playlist_path()).exists())

    async def test_rename_persists_tracks_and_index_without_changing_queue(self):
        before = Playlist(11, "Before")
        after = Playlist(11, "After")
        self.assertTrue(before.save())
        self.assertTrue(after.save())
        self.assertTrue(
            self.playlist.save_available_playlists(["Before", "Favorites", "After"])
        )
        queue = Playlist(11, "Favorites")
        queue.add_track("Active", "https://example.com/active")
        queue.jump_to(0)
        self.cog.players["11"] = SimpleNamespace(get_playlist=lambda: queue)
        await self.run_command()
        self.acl.assert_awaited_once_with(Rule.MUSIC_PLAYLIST_RENAME, self.interaction)
        renamed = Playlist(11, "Renamed")
        self.assertTrue(renamed.load_from_storage())
        self.assertEqual(renamed.get_tracks(), self.playlist.get_tracks())
        self.assertEqual(renamed.get_name(), "Renamed")
        self.assertEqual(
            renamed.get_available_playlists(), ["Before", "Renamed", "After"]
        )
        self.assertFalse(Playlist(11, "Favorites").load_from_storage())
        self.assertEqual(queue.get_name(), "Favorites")
        self.assertEqual(queue.get_tracks()[0]["title"], "Active")
        self.assertEqual(queue.get_current_track_index(), 0)
        self.assertIn("renamed", self.respond.await_args.args[1])

    async def test_existing_destination_is_not_overwritten(self):
        destination = Playlist(11, "Renamed")
        destination.add_track("Other", "https://example.com/other")
        self.assertTrue(destination.save())
        original_destination = Path(destination.get_playlist_path()).read_bytes()
        await self.run_command()
        self.assertEqual(
            Path(destination.get_playlist_path()).read_bytes(), original_destination
        )
        self.assertEqual(
            Path(self.playlist.get_playlist_path()).read_bytes(), self.original
        )
        self.assertIn("already exists", self.respond.await_args.args[1])

    async def test_guilds_are_isolated(self):
        await self.run_command()
        self.assertFalse(Playlist(22, "Renamed").load_from_storage())
        self.assertEqual(Playlist(22).get_available_playlists(), [])

    async def test_missing_playlist_reports_error(self):
        await self.run_command(name="Missing")
        self.assertIn("not found", self.respond.await_args.args[1])
        self.assert_original_preserved()

    async def test_same_name_is_a_noop(self):
        await self.run_command(new_name="Favorites")
        self.assertIn("already named", self.respond.await_args.args[1])
        self.assert_original_preserved()

    async def test_invalid_names_are_rejected(self):
        for name, new_name in (
            ("Favorites", ""),
            ("", "Renamed"),
            ("Favorites", "Invalid\n"),
            ("Invalid\n", "Renamed"),
        ):
            with self.subTest(name=name, new_name=new_name):
                await self.run_command(name, new_name)
                self.assertIn("Invalid format", self.respond.await_args.args[1])
                self.assert_original_preserved()

    async def test_acl_denial_does_not_rename(self):
        self.acl.return_value = False
        await self.run_command()
        self.respond.assert_not_awaited()
        self.assert_original_preserved()

    async def test_dm_does_not_access_guild(self):
        self.server.return_value = False
        self.interaction.guild = None
        await self.run_command()
        self.acl.assert_not_awaited()
        self.assert_original_preserved()

    async def test_admin_role_is_required(self):
        checks = MusicCog.playlist_rename.checks
        self.assertEqual(len(checks), 1)
        self.assertTrue(checks[0](self.interaction))
        self.interaction.user.roles = []
        with self.assertRaises(discord.app_commands.MissingRole):
            checks[0](self.interaction)

    async def test_index_failure_preserves_original_and_removes_destination(self):
        with patch(
            "hifisuperstar.core.Music.Playlist.os.replace",
            side_effect=OSError("disk full"),
        ):
            await self.run_command()
        self.assertIn("Failed to rename", self.respond.await_args.args[1])
        self.assert_original_preserved()
        self.assertEqual(len(list(Path("storage/playlists/11").iterdir())), 2)

    async def test_old_file_removal_failure_rolls_back_index(self):
        old_path = self.playlist.get_playlist_path()
        remove = os.remove

        def fail_old(path):
            if path == old_path:
                raise OSError("permission denied")
            remove(path)

        with patch("hifisuperstar.core.Music.Playlist.os.remove", side_effect=fail_old):
            await self.run_command()
        self.assertIn("Failed to rename", self.respond.await_args.args[1])
        self.assert_original_preserved()

    def test_model_refuses_unlisted_destination_file(self):
        destination = Playlist(11, "Renamed")
        self.assertTrue(destination.save(cache=True))
        self.assertFalse(self.playlist.rename("Renamed"))
        self.assertEqual(
            json.loads(Path(destination.get_playlist_path()).read_text())["name"],
            "Renamed",
        )

    async def test_corrupt_playlist_reports_error_without_touching_index(self):
        Path(self.playlist.get_playlist_path()).write_text("invalid JSON")
        await self.run_command()
        self.assertIn("ERROR", self.respond.await_args.args[1])
        self.assertEqual(self.playlist.get_available_playlists(), ["Favorites"])

    def test_destination_write_failure_leaves_original_intact(self):
        with patch(
            "hifisuperstar.core.Music.Playlist.json.dump",
            side_effect=OSError("disk full"),
        ):
            self.assertFalse(self.playlist.rename("Renamed"))
        self.assert_original_preserved()

    def test_save_and_delete_still_update_the_atomic_index(self):
        other = Playlist(11, "Other")
        self.assertTrue(other.save())
        self.assertEqual(other.get_available_playlists(), ["Favorites", "Other"])
        self.assertTrue(other.delete())
        self.assert_original_preserved()


if __name__ == "__main__":
    unittest.main()
