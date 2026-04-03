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
        self.responses = load_resource('regex', 'responses')
        self.setup_events()

    def setup_events(self):
        Events.add_event('on_message', self.on_message)
        return

    async def on_message(self, message):
        info(self, f"Message received {message if self.config['RegexCog']['Log_Messages'] else ''}")

        if not message.author.bot:
            for key in self.responses:
                if re.match(self.responses[key]['match'], message.content):
                    info(self, f"Message response match {self.responses[key]}")
                    await message.channel.send(self.responses[key]['response'], reference=message)

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

        self.responses[str_rand_crc32()] = {
            'match': match,
            'response': response
        }

        try:
            save_resource('regex', 'responses', self.responses)
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

        if item_id not in self.responses:
            error(self, f"No matches found for id {item_id}")
            return await respond(interaction, 'Item not found.')

        self.responses.pop(item_id)

        try:
            save_resource('regex', 'responses', self.responses)
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

        if len(self.responses) == 0:
            return await respond(interaction, 'There are no responses available.')
        info(self, self.responses)
        message = 'Current regex responses: ```'
        for key in self.responses:
            message += f"{key}: '{self.responses[key]['match']}' responds with '{self.responses[key]['response']}'\n"
        message += '```'

        await respond(interaction, message)
