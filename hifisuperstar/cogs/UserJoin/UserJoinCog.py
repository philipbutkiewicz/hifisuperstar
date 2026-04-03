#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
from discord import app_commands
from discord.ext import commands

from hifisuperstar.core.Server.Events import Events
from hifisuperstar.core.Server.Server import check_server, respond
from hifisuperstar.io.Logger import error, warn
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Resources import load_resource, save_resource


class UserJoinCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config

        Events.add_event('on_member_join', self.on_member_join)

    async def on_member_join(self, member):
        userjoin = load_resource('userjoin', member.guild)

        info(self, f"User {member} has joined the server", member.guild.id)
        if 'enabled' not in userjoin:
            warn(self, 'Event warning: User join cog has not been configured', member.guild)
            return False

        if 'channel' not in userjoin:
            error(self, 'Event error: Channel name has not been configured', member.guild)
            return False

        if not userjoin['enabled']:
            warn(self, 'Event warning: User join cog has not been enabled', member.guild)
            return False

        channel = discord.utils.get(member.guild.text_channels, name=userjoin['name'])
        if not channel:
            error(self, f"Event error: Could not find the configured channel {userjoin['name']}")
            return False

        return await channel.send(f"{member} has joined the server")

    @app_commands.command(name='set_userjoin_channel', description='Configures the channel to send messages to')
    @app_commands.checks.has_role('Admin')
    async def set_userjoin_channel(self, interaction: discord.Interaction, channel: str):
        info(self, 'Set user join channel request', interaction.guild)

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not discord.utils.get(interaction.guild.text_channels, name=channel):
            error(self, f"Channel {channel} does not exist")
            return await respond(interaction, f"Channel {channel} does not exist!")

        save_resource('userjoin', interaction.guild.id, {'channel': channel, 'enabled': True})

        await respond(interaction, f"Channel {channel} has been set.")

    @app_commands.command(name='disable_userjoin', description='Disables the user join cog')
    @app_commands.checks.has_role('Admin')
    async def disable_userjoin(self, interaction: discord.Interaction):
        info(self, 'Disable user join channel request', interaction.guild)

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        save_resource('userjoin', interaction.guild.id, {'channel': None, 'enabled': False})

        await respond(interaction, 'User join has been disabled.')
