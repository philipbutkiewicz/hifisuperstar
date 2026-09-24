#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#
import re

import discord
from discord import app_commands
from hifisuperstar.core.Server.Events import Events
from hifisuperstar.core.Server.Server import check_server, respond
from hifisuperstar.io.Logger import info, error
from discord.ext import commands

from hifisuperstar.io.Resources import load_resource, save_resource
from hifisuperstar.io.Strings import str_rand_crc32


class RegexCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.guild_responses = {}
        self.setup_events()

    def get_responses(self, guild_id):
        if guild_id not in self.guild_responses:
            self.guild_responses[guild_id] = load_resource('regex', guild_id)

        return self.guild_responses[guild_id]

    def setup_events(self):
        Events.add_event('on_message', self.on_message)
        return

    async def on_message(self, message):
        info(self, f"Message received {message if self.config['RegexCog']['Log_Messages'] else ''}")

        if message.guild is None or message.author.bot:
            return

        responses = self.get_responses(message.guild.id)
        for key in responses:
            if re.match(responses[key]['match'], message.content):
                info(self, f"Message response match {responses[key]}")
                await message.channel.send(responses[key]['response'], reference=message)

    @app_commands.command(name='set_regex_response', description='Sets an regex response')
    @app_commands.checks.has_role('Admin')
    async def set_regex_response(self, interaction: discord.Interaction, match: str, response: str):
        info(self, 'Set regex response request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not re.compile(match):
            error(self, f"Failed to compile regex '{match}'")
            return await respond(interaction, 'Invalid regular expression.')

        responses = self.get_responses(interaction.guild.id)
        responses[str_rand_crc32()] = {
            'match': match,
            'response': response
        }

        try:
            save_resource('regex', interaction.guild.id, responses)
        except Exception as e:
            error(self, f"Failed to save regex responses: {e}")
            return await respond(interaction, 'ERROR: Could not save responses')

        await respond(interaction, 'Response set!')

    @app_commands.command(name='delete_regex_response', description='Deletes an regex response')
    @app_commands.checks.has_role('Admin')
    async def delete_regex_response(self, interaction: discord.Interaction, item_id: str):
        info(self, 'Delete regex response request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if item_id not in self.get_responses(interaction.guild.id):
            error(self, f"No matches found for id {item_id}")
            return await respond(interaction, 'Item not found.')

        responses = self.get_responses(interaction.guild.id)
        responses.pop(item_id)

        try:
            save_resource('regex', interaction.guild.id, responses)
        except Exception as e:
            error(self, f"Failed to save regex responses: {e}")
            return await respond(interaction, 'ERROR: Could not save responses')

        await respond(interaction, 'Deleted!')

    @app_commands.command(name='list_regex_responses', description='Lists all regex responses')
    async def list_regex_responses(self, interaction: discord.Interaction):
        info(self, 'List regex responses request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        responses = self.get_responses(interaction.guild.id)
        if len(responses) == 0:
            return await respond(interaction, 'There are no responses available.')
        info(self, responses)

        lines = [
            f"`{key}` — match: `{responses[key]['match']}` → `{responses[key]['response']}`"
            for key in responses
        ]
        embed = discord.Embed(
            title='Regex Responses',
            description='\n'.join(lines),
            color=discord.Color.blurple()
        )
        await respond(interaction, embed=embed)
