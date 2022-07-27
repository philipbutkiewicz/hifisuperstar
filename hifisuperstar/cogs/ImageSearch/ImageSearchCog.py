# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2022 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import random
from discord.ext import commands
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import warn
from hifisuperstar.io.Logger import error
from hifisuperstar.core.Acl.Acl import Acl
from hifisuperstar.core.Acl import Rule
from hifisuperstar.core.Server.Server import check_server
from duckduckgo_search import ddg_images


class ImageSearchCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config

    def find_image(self, query):
        return ddg_images(query, region='wt-wt', safesearch=self.config['ImageSearchCog']['Safe_Search'], time=None,
                          size=None,
                          color=None, type_image=None, layout=None, license_image=None, max_results=100)

    @commands.slash_command(description='Displays the current image search config')
    async def image_search_config(self, ctx):
        info(self, 'Image search config request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        info(self, 'Displaying search configuration', ctx.guild)
        await ctx.respond(
            f"**Current image search configuration**\nMax items: {self.config['ImageSearchCog']['Max_Results']}\nSafe "
            f"search: {self.config['ImageSearchCog']['Safe_Search']}")

    @commands.slash_command(description='Conducts an image search')
    async def image_search(self, ctx, query, item_index=0, max_items=1):
        info(self, 'Image search request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.IMAGE_SEARCH, ctx):
            return False

        info(self, f"Image search request: '{query}' {item_index}/{max_items}", ctx.guild)

        if not type(max_items) == int:
            warn(self, 'Invalid input', ctx.guild)
            return await ctx.respond('ERROR: max_items must be an integer.')

        if not type(item_index) == int:
            warn(self, 'Invalid input', ctx.guild)
            return await ctx.respond('ERROR: item_index must be an integer.')

        if max_items > int(self.config['ImageSearchCog']['Max_Results']) or max_items <= 0:
            warn(self, 'Invalid input', ctx.guild)
            return await ctx.respond(
                f"ERROR: Invalid request, you can display up "
                f"to {self.config['ImageSearchCog']['Max_Results']} at once.")

        await ctx.respond('Hold on, looking that up...')

        images = self.find_image(query)

        if len(images) == 0:
            return await ctx.respond('No results found.')

        if item_index > len(images) - 1 or item_index + (max_items - 1) > len(images) - 1:
            warn(self, 'Invalid input', ctx.guild)
            return await ctx.respond(f"ERROR: Index out of range, max index is {len(images) - 1}")

        await ctx.respond(f"{len(images)} results for '{query}', displaying index {item_index}")
        for i in range(item_index, item_index + max_items):
            await ctx.respond(f"{images[i]['title']}\n{images[i]['image']}")

    @commands.slash_command(description='Conducts a random image search')
    async def random_image_search(self, ctx, query):
        info(self, 'Random mage search request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.IMAGE_SEARCH, ctx):
            return False

        info(self, f"Random image search request: '{query}'", ctx.guild)

        await ctx.respond('Hold on, looking that up...')

        images = self.find_image(query)

        if len(images) == 0:
            return await ctx.respond('No results found.')

        i = random.randint(0, len(images))
        await ctx.respond(f"{images[i]['title']}\n{images[i]['image']}")
