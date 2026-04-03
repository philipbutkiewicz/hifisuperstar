# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import random
import discord
from discord import app_commands
from discord.ext import commands
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import warn
from hifisuperstar.io.Logger import error
from hifisuperstar.core.Acl.Acl import Acl
from hifisuperstar.core.Acl import Rule
from hifisuperstar.core.Server.Server import check_server, respond
from duckduckgo_search import DDGS


class ImageSearchCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config

    def find_image(self, query):
        return DDGS().images(query, region='wt-wt', safesearch=self.config['ImageSearchCog']['Safe_Search'],
                             timelimit=None, size=None, color=None, type_image=None, layout=None,
                             license_image=None, max_results=100)

    @app_commands.command(name='image_search_config', description='Displays the current image search config')
    async def image_search_config(self, interaction: discord.Interaction):
        info(self, 'Image search config request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        info(self, 'Displaying search configuration', interaction.guild)
        await respond(interaction,
            f"**Current image search configuration**\nMax items: {self.config['ImageSearchCog']['Max_Results']}\nSafe "
            f"search: {self.config['ImageSearchCog']['Safe_Search']}")

    @app_commands.command(name='image_search', description='Conducts an image search')
    async def image_search(self, interaction: discord.Interaction, query: str, item_index: int = 0, max_items: int = 1):
        info(self, 'Image search request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.IMAGE_SEARCH, interaction):
            return False

        info(self, f"Image search request: '{query}' {item_index}/{max_items}", interaction.guild)

        if not type(max_items) == int:
            warn(self, 'Invalid input', interaction.guild)
            return await respond(interaction, 'ERROR: max_items must be an integer.')

        if not type(item_index) == int:
            warn(self, 'Invalid input', interaction.guild)
            return await respond(interaction, 'ERROR: item_index must be an integer.')

        if max_items > int(self.config['ImageSearchCog']['Max_Results']) or max_items <= 0:
            warn(self, 'Invalid input', interaction.guild)
            return await respond(interaction,
                f"ERROR: Invalid request, you can display up "
                f"to {self.config['ImageSearchCog']['Max_Results']} at once.")

        await respond(interaction, 'Hold on, looking that up...')

        images = self.find_image(query)

        if len(images) == 0:
            return await respond(interaction, 'No results found.')

        if item_index > len(images) - 1 or item_index + (max_items - 1) > len(images) - 1:
            warn(self, 'Invalid input', interaction.guild)
            return await respond(interaction, f"ERROR: Index out of range, max index is {len(images) - 1}")

        await respond(interaction, f"{len(images)} results for '{query}', displaying index {item_index}")
        for i in range(item_index, item_index + max_items):
            await respond(interaction, f"{images[i]['title']}\n{images[i]['image']}")

    @app_commands.command(name='random_image_search', description='Conducts a random image search')
    async def random_image_search(self, interaction: discord.Interaction, query: str):
        info(self, 'Random mage search request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.IMAGE_SEARCH, interaction):
            return False

        info(self, f"Random image search request: '{query}'", interaction.guild)

        await respond(interaction, 'Hold on, looking that up...')

        images = self.find_image(query)

        if len(images) == 0:
            return await respond(interaction, 'No results found.')

        i = random.randint(0, len(images))
        await respond(interaction, f"{images[i]['title']}\n{images[i]['image']}")
