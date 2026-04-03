#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
import re
from discord import app_commands
from discord.ext import commands
from hifisuperstar.cogs.Spotify.Spotify.Client import Client
from hifisuperstar.core.Acl.Acl import Acl
from hifisuperstar.core.Acl import Rule

from hifisuperstar.core.Server.Events import Events
from hifisuperstar.core.Server.Server import check_server, respond
from hifisuperstar.io.Logger import error
from hifisuperstar.io.Logger import warn
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Strings import allowed_chars_regex


class SpotifyCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.client = Client(config)

    @app_commands.command(name='spotify_import_playlist', description='Imports a Spotify playlist')
    async def spotify_import_playlist(self, interaction: discord.Interaction, playlist_url: str):
        info(self, 'Spotify playlist import request', interaction.guild)

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.SPOTIFY_IMPORT_PLAYLIST, interaction):
            return False
        
        info(self, f"Getting Spotify playlist with URL '{playlist_url}'", interaction.guild)
        playlist = self.client.get_playlist(interaction, self.client.get_birdy_uri(playlist_url))

        if not playlist:
            error(self, f"Failed getting a Spotify playlist with URL '{playlist_url}'!")
            return await respond(interaction, 'Sorry, something went wrong. Couldn\'t fetch your playlist from Spotify.')
        
        if not re.match(allowed_chars_regex, playlist.name):
            warn(self, 'Invalid input', interaction.guild)
            return await respond(interaction, f"The playlist name '{playlist.name}' contains illegal characters, please limit the playlist name to alphanumeric characters and some allowed symbols (space, comma, exclamation mark, dash, underscore)")
        
        if not playlist.save():
            error(self, 'Failed to save the playlist', interaction.guild)
            return await respond(interaction, f"ERROR: Failed to save playlist '{playlist.name}'")

        return await respond(interaction, 'Your playlist has been imported and saved!')
        
