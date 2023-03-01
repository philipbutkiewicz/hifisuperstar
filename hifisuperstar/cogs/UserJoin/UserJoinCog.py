#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
from discord.ext import commands

from hifisuperstar.core.Server.Events import Events
from hifisuperstar.core.Server.Server import check_server
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

    @commands.slash_command(description='Configures the channel to send messages to')
    @commands.has_role('Admin')
    async def set_userjoin_channel(self, ctx, channel):
        info(self, 'Set user join channel request', ctx.guild)

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not discord.utils.get(ctx.guild.text_channels, name=channel):
            error(self, f"Channel {channel} does not exist")
            return await ctx.respond(f"Channel {channel} does not exist!")

        save_resource('userjoin', ctx.guild.id, {'channel': channel, 'enabled': True})

        await ctx.respond(f"Channel {channel} has been set.")

    @commands.slash_command(description='Disables the user join cog')
    @commands.has_role('Admin')
    async def disable_userjoin(self, ctx):
        info(self, 'Disable user join channel request', ctx.guild)

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        save_resource('userjoin', ctx.guild.id, {'channel': None, 'enabled': False})

        await ctx.respond('User join has been disabled.')
