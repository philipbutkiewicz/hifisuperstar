#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from flask import Flask

from hifisuperstar.cogs.ImageSearch.ImageSearchCog import ImageSearchCog
from hifisuperstar.cogs.Jokes.JokesCog import JokesCog
from hifisuperstar.cogs.LLM.Tools.ImageSearchTool import create_image_search_tool
from hifisuperstar.cogs.LLM.Tools.MusicTool import create_music_tools
from hifisuperstar.cogs.Music.MusicCog import MusicCog
from hifisuperstar.cogs.RandomPictures.RandomPicturesCog import RandomPicturesCog
from hifisuperstar.cogs.Regex.RegexCog import RegexCog
from hifisuperstar.cogs.Spotify.Spotify.Client import Client
from hifisuperstar.cogs.Spotify.SpotifyCog import SpotifyCog
from hifisuperstar.core.Acl.Acl import Acl
from hifisuperstar.core.Music.PlayCounter import PlayCounter
from hifisuperstar.core.Music.Player import Player
from hifisuperstar.core.Music.Playlist import Playlist
from hifisuperstar.io.GuildConfig import get_guild_config
from hifisuperstar.io.Resources import load_resource
from web.controllers.PlaylistController import PlaylistController


def interaction(guild_id):
    return SimpleNamespace(guild=SimpleNamespace(id=guild_id, name=str(guild_id)))


class BotFeatureTests(unittest.TestCase):
    def setUp(self):
        self.previous_directory = os.getcwd()
        self.directory = tempfile.TemporaryDirectory()
        os.chdir(self.directory.name)
        os.mkdir("storage")

    def tearDown(self):
        os.chdir(self.previous_directory)
        self.directory.cleanup()

    def test_acl_rules_and_admin_mode_are_guild_specific(self):
        first = Acl(11)
        first.set_rule("PLAY", "0", 123)
        first.save_rules()
        self.assertFalse(Acl(11).is_allowed("PLAY", 123, True))
        self.assertTrue(Acl(22).is_allowed("PLAY", 123, True))
        first.toggle_admin_mode()
        first.save_rules()
        self.assertFalse(Acl(11).is_allowed("PLAY", 456, True))
        self.assertTrue(Acl(22).is_allowed("PLAY", 456, True))
        first.clear()
        first.save_rules()
        self.assertTrue(Acl(11).is_allowed("PLAY", 123, True))

    def test_regex_command_and_event_only_affect_their_guild(self):
        cog = RegexCog.__new__(RegexCog)
        cog.config = {"RegexCog": {"Log_Messages": False}}
        cog.guild_responses = {}
        sent = AsyncMock()

        async def run():
            with (
                patch(
                    "hifisuperstar.cogs.Regex.RegexCog.check_server",
                    new=AsyncMock(return_value=True),
                ),
                patch("hifisuperstar.cogs.Regex.RegexCog.respond", new=AsyncMock()),
            ):
                await RegexCog.set_regex_response.callback(
                    cog, interaction(11), "^ping", "pong"
                )
                for guild_id in (11, 22):
                    message = SimpleNamespace(
                        guild=SimpleNamespace(id=guild_id),
                        author=SimpleNamespace(bot=False),
                        content="ping",
                        channel=SimpleNamespace(send=sent),
                    )
                    await cog.on_message(message)

        asyncio.run(run())
        sent.assert_awaited_once()
        self.assertEqual(len(load_resource("regex", 11)), 1)
        self.assertEqual(load_resource("regex", 22), {})

    def test_music_players_play_counts_and_playlists_are_guild_specific(self):
        cog = MusicCog.__new__(MusicCog)
        cog.config = {}
        cog.players = {}
        with (
            patch(
                "hifisuperstar.cogs.Music.MusicCog.check_server",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "hifisuperstar.cogs.Music.MusicCog.Player",
                side_effect=[object(), object()],
            ),
        ):
            first = asyncio.run(cog.get_player(interaction(11)))
            self.assertIs(first, asyncio.run(cog.get_player(interaction(11))))
            self.assertIsNot(first, asyncio.run(cog.get_player(interaction(22))))

        track = {"id": "song", "url": "https://example.com/song", "title": "Song"}
        PlayCounter(11).count_playback(track)
        self.assertEqual(PlayCounter(11).get_all_counts()["song"]["count"], 1)
        self.assertEqual(PlayCounter(22).get_all_counts(), {})

        playlist = Playlist(11, "Favorites")
        playlist.add_track("Song", track["url"])
        self.assertTrue(playlist.save())
        self.assertTrue(Playlist(11, "Favorites").load_from_storage())
        self.assertFalse(Playlist(22, "Favorites").load_from_storage())
        self.assertEqual(Playlist(22).get_available_playlists(), [])

    def test_web_playlist_lookup_stays_inside_its_guild(self):
        playlist = Playlist(11, "Favorites")
        playlist.add_track("Song", "https://example.com/song")
        self.assertTrue(playlist.save())

        app = Flask(__name__)
        app.config["BASE_APP_PATH"] = "."
        with app.app_context():
            controller = PlaylistController()
            self.assertEqual(
                controller.load_playlist("Favorites", "11")["guild_id"], "11"
            )
            self.assertIsNone(controller.load_playlist("Favorites", "22"))

    def test_music_playback_configuration_uses_guild_override(self):
        config = {
            "MusicCog": {
                "Radio_URL": "https://default/radio",
                "Allowed_Mime_Types": ["audio/mpeg"],
            },
            "Guilds": {
                "22": {
                    "MusicCog": {
                        "Radio_URL": "https://other/radio",
                        "Allowed_Mime_Types": ["audio/flac"],
                    }
                }
            },
        }
        first = Player(interaction(11), config)
        second = Player(interaction(22), config)
        self.assertEqual(first.music_config["Allowed_Mime_Types"], ["audio/mpeg"])
        self.assertEqual(second.music_config["Allowed_Mime_Types"], ["audio/flac"])
        for player, url in (
            (first, "https://default/radio"),
            (second, "https://other/radio"),
        ):
            player.interaction.guild.voice_client = SimpleNamespace(
                is_playing=lambda: False
            )
            with patch.object(player, "play_track") as play_track:
                player.queue_radio()
                play_track.assert_called_once_with(url)

    def test_spotify_import_builds_playlist_for_requesting_guild(self):
        client = Client({})
        spotify = MagicMock()
        spotify.playlist.return_value = {
            "name": "Favorites",
            "tracks": {
                "items": [{"track": {"artists": [{"name": "Band"}], "name": "Song"}}]
            },
        }
        with patch.object(
            client, "get_spotify_client", return_value=spotify
        ) as get_client:
            playlist = client.get_playlist(interaction(11), "spotify:playlist:abc")
        get_client.assert_called_once_with(11)
        self.assertEqual(playlist.guild_id, "11")
        self.assertEqual(playlist.get_tracks()[0]["title"], "Band - Song")
        self.assertTrue(playlist.save())
        self.assertFalse(Playlist(22, playlist.name).load_from_storage())

    def test_spotify_credentials_are_selected_by_guild(self):
        client = Client(
            {
                "SpotifyCog": {"Client_ID": "default", "Client_Secret": "shared"},
                "Guilds": {"22": {"SpotifyCog": {"Client_ID": "other"}}},
            }
        )
        with (
            patch(
                "hifisuperstar.cogs.Spotify.Spotify.Client.SpotifyClientCredentials"
            ) as credentials,
            patch(
                "hifisuperstar.cogs.Spotify.Spotify.Client.spotipy.Spotify"
            ) as spotify,
        ):
            client.get_spotify_client(11)
            credentials.assert_called_with("default", "shared")
            client.get_spotify_client(22)
            credentials.assert_called_with("other", "shared")
            self.assertEqual(spotify.call_count, 2)

    def test_spotify_command_saves_playlist_for_requesting_guild(self):
        cog = SpotifyCog.__new__(SpotifyCog)
        playlist = Playlist(22, "Spotify - Favorites")
        playlist.add_track("Song", "https://example.com/song")
        cog.client = SimpleNamespace(
            get_birdy_uri=lambda url: "spotify:playlist:abc",
            get_playlist=lambda request, uri: playlist,
        )

        async def run():
            with (
                patch(
                    "hifisuperstar.cogs.Spotify.SpotifyCog.check_server",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "hifisuperstar.cogs.Spotify.SpotifyCog.Acl.check_and_fail",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "hifisuperstar.cogs.Spotify.SpotifyCog.respond", new=AsyncMock()
                ) as respond,
            ):
                await SpotifyCog.spotify_import_playlist.callback(
                    cog, interaction(22), "https://open.spotify.com/playlist/abc"
                )
                self.assertIn("imported and saved", respond.await_args.args[1])

        asyncio.run(run())
        self.assertTrue(Playlist(22, playlist.name).load_from_storage())
        self.assertFalse(Playlist(11, playlist.name).load_from_storage())

    def test_llm_music_tools_read_only_the_message_guild_queue(self):
        first_playlist = MagicMock()
        first_playlist.get_tracks.return_value = [{"id": "1", "title": "First"}]
        first_playlist.get_current_track.return_value = {"id": "1", "title": "First"}
        first_player = MagicMock()
        first_player.get_playlist.return_value = first_playlist
        music = SimpleNamespace(players={"11": first_player}, config={})
        for guild_id, expected in ((11, "First"), (22, "Nothing is in the queue")):
            message = SimpleNamespace(guild=SimpleNamespace(id=guild_id))
            tools = {tool.name: tool for tool in create_music_tools(music, message)}
            self.assertIn(expected, tools["music_get_queue"].invoke({}))

    def test_nested_music_s3_defaults_are_merged_per_guild(self):
        config = {
            "MusicCog": {"S3": {"Enabled": False, "Bucket": "base", "Region": "eu"}},
            "Guilds": {
                "22": {"MusicCog": {"S3": {"Enabled": True, "Bucket": "other"}}}
            },
        }
        first = get_guild_config(config, "MusicCog", 11)["S3"]
        second = get_guild_config(config, "MusicCog", 22)["S3"]
        self.assertEqual(first, {"Enabled": False, "Bucket": "base", "Region": "eu"})
        self.assertEqual(second, {"Enabled": True, "Bucket": "other", "Region": "eu"})
        self.assertEqual(config["MusicCog"]["S3"]["Bucket"], "base")

    def test_music_download_uses_guild_s3_configuration(self):
        cog = MusicCog.__new__(MusicCog)
        cog.config = {
            "MusicCog": {"S3": {"Enabled": False, "Bucket": "default"}},
            "Guilds": {
                "22": {"MusicCog": {"S3": {"Enabled": True, "Bucket": "other"}}}
            },
        }

        async def run():
            with (
                patch(
                    "hifisuperstar.cogs.Music.MusicCog.check_server",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "hifisuperstar.cogs.Music.MusicCog.Acl.check_and_fail",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "hifisuperstar.cogs.Music.MusicCog.respond", new=AsyncMock()
                ) as respond,
                patch(
                    "hifisuperstar.cogs.Music.MusicCog.asyncio.to_thread",
                    new=AsyncMock(return_value=[]),
                ) as listing,
            ):
                await MusicCog.playlist_downloads.callback(cog, interaction(11))
                listing.assert_not_awaited()
                await MusicCog.playlist_downloads.callback(cog, interaction(22))
                self.assertEqual(listing.await_args.args[1]["Bucket"], "other")
                self.assertEqual(listing.await_args.args[2], "22")
                self.assertIn("No playlist packages", respond.await_args.args[1])

        asyncio.run(run())

    def test_music_playlist_web_link_uses_guild_configuration(self):
        cog = MusicCog.__new__(MusicCog)
        cog.config = {
            "Web": {"Enabled": False, "Base_Url": "https://default"},
            "Guilds": {"22": {"Web": {"Enabled": True, "Base_Url": "https://other"}}},
        }
        player = MagicMock()
        player.get_playlist.return_value.get_available_playlists.return_value = [
            "Favorites"
        ]

        async def run():
            with (
                patch(
                    "hifisuperstar.cogs.Music.MusicCog.check_server",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "hifisuperstar.cogs.Music.MusicCog.Acl.check_and_fail",
                    new=AsyncMock(return_value=True),
                ),
                patch.object(cog, "get_player", new=AsyncMock(return_value=player)),
                patch(
                    "hifisuperstar.cogs.Music.MusicCog.respond", new=AsyncMock()
                ) as respond,
            ):
                await MusicCog.list_playlists.callback(cog, interaction(11))
                self.assertEqual(respond.await_args.kwargs["embed"].fields, [])
                await MusicCog.list_playlists.callback(cog, interaction(22))
                self.assertIn(
                    "https://other/playlists/22",
                    respond.await_args.kwargs["embed"].fields[0].value,
                )

        asyncio.run(run())

    def test_llm_image_tool_uses_guild_safesearch(self):
        config = {
            "ImageSearchCog": {"Safe_Search": "Moderate"},
            "Guilds": {"22": {"ImageSearchCog": {"Safe_Search": "Strict"}}},
        }
        with patch("hifisuperstar.cogs.LLM.Tools.ImageSearchTool.DDGS") as ddgs:
            ddgs.return_value.images.return_value = []
            for guild_id, expected in ((11, "Moderate"), (22, "Strict")):
                tool = create_image_search_tool(
                    get_guild_config(config, "ImageSearchCog", guild_id)["Safe_Search"]
                )
                self.assertEqual(tool.invoke({"query": "photo"}), "No images found.")
                self.assertEqual(
                    ddgs.return_value.images.call_args.kwargs["safesearch"], expected
                )

    def test_jokes_and_image_search_respond_in_requesting_guild(self):
        jokes = JokesCog.__new__(JokesCog)
        jokes.config = {
            "JokesCog": {"Allowed_Joke_Types": ["dad"]},
            "Guilds": {"22": {"JokesCog": {"Allowed_Joke_Types": []}}},
        }
        jokes.jokes = {"dad": ["A joke"]}
        images = ImageSearchCog.__new__(ImageSearchCog)
        images.config = {
            "ImageSearchCog": {"Max_Results": 2, "Safe_Search": "Moderate"},
            "Guilds": {
                "22": {"ImageSearchCog": {"Max_Results": 1, "Safe_Search": "Strict"}}
            },
        }

        async def run():
            with (
                patch(
                    "hifisuperstar.cogs.Jokes.JokesCog.check_server",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "hifisuperstar.cogs.Jokes.JokesCog.respond", new=AsyncMock()
                ) as joke_response,
                patch(
                    "hifisuperstar.cogs.ImageSearch.ImageSearchCog.check_server",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "hifisuperstar.cogs.ImageSearch.ImageSearchCog.respond",
                    new=AsyncMock(),
                ) as image_response,
                patch(
                    "hifisuperstar.cogs.ImageSearch.ImageSearchCog.Acl.check_and_fail",
                    new=AsyncMock(return_value=True),
                ),
                patch.object(
                    images,
                    "find_image",
                    return_value=[{"title": "Photo", "image": "https://example.com/p"}],
                ) as find_image,
            ):
                await JokesCog.dad.callback(jokes, interaction(11))
                await ImageSearchCog.image_search.callback(
                    images, interaction(22), "photo"
                )
                self.assertEqual(joke_response.await_args.args[0].guild.id, 11)
                await JokesCog.dad.callback(jokes, interaction(22))
                self.assertIn("no dad jokes", joke_response.await_args.args[1])
                self.assertTrue(
                    all(
                        call.args[0].guild.id == 22
                        for call in image_response.await_args_list
                    )
                )
                find_image.assert_called_once_with("photo", 22)
                await ImageSearchCog.image_search.callback(
                    images, interaction(22), "photo", max_items=2
                )
                find_image.assert_called_once()
                self.assertIn("up to 1", image_response.await_args.args[1])

        asyncio.run(run())

    def test_random_pictures_respond_in_requesting_guild(self):
        cog = RandomPicturesCog.__new__(RandomPicturesCog)
        cog.config = {
            "RandomPicturesCog": {
                "Enabled_Picture_Types": ["cat"],
                "Allowed_File_Types": ["jpg"],
            },
            "Guilds": {"22": {"RandomPicturesCog": {"Enabled_Picture_Types": []}}},
        }

        async def run():
            with (
                patch(
                    "hifisuperstar.cogs.RandomPictures.RandomPicturesCog.check_server",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "hifisuperstar.cogs.RandomPictures.RandomPicturesCog.respond",
                    new=AsyncMock(),
                ) as response,
                patch(
                    "hifisuperstar.cogs.RandomPictures.RandomPicturesCog.asyncio.to_thread",
                    new=AsyncMock(return_value=(b"image", "cat.jpg")),
                ),
                patch.object(
                    cog,
                    "load_pictures",
                    side_effect=lambda settings: (
                        {"cat": ["cat.jpg"]}
                        if settings["Enabled_Picture_Types"]
                        else {}
                    ),
                ),
            ):
                await RandomPicturesCog.cat.callback(cog, interaction(11))
                self.assertEqual(response.await_args.args[0].guild.id, 11)
                self.assertEqual(response.await_args.kwargs["file"].filename, "cat.jpg")
                await RandomPicturesCog.cat.callback(cog, interaction(22))
                self.assertIn("no cat pictures", response.await_args.args[1])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
