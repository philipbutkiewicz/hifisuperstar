# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import random
from discord.ext import commands
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import error
from hifisuperstar.core.Server.Server import check_server
from hifisuperstar.io.Resources import load_resource


class KenjaCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.kenja_values = load_resource('res', 'kenja_values')
        if not self.kenja_values:
            raise Exception('Kenja Values database is corrupt')

    @commands.slash_command(description='Kenja Values')
    async def kenja(self, ctx):
        info(self, 'Kenja Values request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        info(self, 'Kenja Values request', ctx.guild)

        if len(self.kenja_values) == 0:
            return await ctx.respond(f"Sorry, there are no Kenja Values available. :(")

        kenja_value = random.choice(self.kenja_values)

        await ctx.respond(f"Ahh, I see you're a man of **Kenja Values** as well...\n``{kenja_value}``")
