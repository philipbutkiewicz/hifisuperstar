#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#
# NOTE: Voice monitoring (discord.sinks / start_recording) is a py-cord-only feature and is not available in discord.py.
# These commands are stubbed out with an informational error message.
#

import discord
from discord import app_commands
from discord.ext import commands
from hifisuperstar.io.Logger import info
from hifisuperstar.core.Server.Server import check_server, respond


class AntiLoudmouthCog(commands.Cog):
    def __init__(self, config, client):
        info(self, 'Registered')
        self.config = config
        self.client = client

    @app_commands.command(name='start_monitoring', description='Starts monitoring voice channel audio for loudmouths')
    @app_commands.checks.has_role('Admin')
    async def start_monitoring(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return False
        await respond(interaction, 'ERROR: Voice monitoring is not supported in discord.py.')

    @app_commands.command(name='stop_monitoring', description='Stops monitoring voice channel audio for loudmouths')
    @app_commands.checks.has_role('Admin')
    async def stop_monitoring(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return False
        await respond(interaction, 'ERROR: Voice monitoring is not supported in discord.py.')

