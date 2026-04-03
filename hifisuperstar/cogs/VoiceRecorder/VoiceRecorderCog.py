#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#
# NOTE: Voice recording (discord.sinks) is a py-cord-only feature and is not available in discord.py.
# These commands are stubbed out with an informational error message.
#

import discord
from discord import app_commands
from discord.ext import commands
from hifisuperstar.io.Logger import info
from hifisuperstar.core.Server.Server import check_server, respond


class VoiceRecorderCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config

    @app_commands.command(name='start_recording', description='Starts recording voice channel audio')
    @app_commands.checks.has_role('Admin')
    async def start_recording(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return False
        await respond(interaction, 'ERROR: Voice recording is not supported in discord.py.')

    @app_commands.command(name='stop_recording', description='Stops recording voice channel audio')
    @app_commands.checks.has_role('Admin')
    async def stop_recording(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return False
        await respond(interaction, 'ERROR: Voice recording is not supported in discord.py.')

