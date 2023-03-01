# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import random

from discord.ext import commands

from hifisuperstar.core.Server.Server import check_server
from hifisuperstar.io.Logger import error
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Resources import load_resource


class JokesCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.jokes = load_resource('res', 'jokes')
        if not self.jokes:
            raise Exception('Joke database is corrupt')

    async def send_joke(self, joke_type, ctx):
        info(self, 'Joke request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        info(self, f"Joke request of the '{joke_type}' type", ctx.guild)

        if joke_type not in self.config['JokesCog']['Allowed_Joke_Types'] or joke_type not in self.jokes or \
                len(self.jokes[joke_type]) == 0:
            return await ctx.respond(f"Sorry, there are no {joke_type} jokes available. :(")

        joke = random.choice(self.jokes[joke_type])

        return await ctx.respond(f"Here is a joke for you: ``{joke}``")

    @commands.slash_command(description='Tells a dad joke')
    async def dad(self, ctx):
        await self.send_joke('dad', ctx)

    @commands.slash_command(description='Tells a Chuck Norris joke')
    async def chuck(self, ctx):
        await self.send_joke('chuck', ctx)

    @commands.slash_command(description='Tells a BAD joke')
    async def badjoke(self, ctx):
        await self.send_joke('bad', ctx)
