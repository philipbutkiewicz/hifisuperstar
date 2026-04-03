# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import random
import discord
from discord import app_commands
from discord.ext import commands
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import error
from hifisuperstar.core.Server.Server import check_server, respond
from hifisuperstar.io.Resources import load_resource


class KenjaCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.kenja_values = load_resource('res', 'kenja_values')
        if not self.kenja_values:
            raise Exception('Kenja Values database is corrupt')

    @app_commands.command(name='kenja', description='Kenja Values')
    async def kenja(self, interaction: discord.Interaction):
        info(self, 'Kenja Values request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        info(self, 'Kenja Values request', interaction.guild)

        if len(self.kenja_values) == 0:
            return await respond(interaction, f"Sorry, there are no Kenja Values available. :(")

        kenja_value = random.choice(self.kenja_values)

        await respond(interaction, f"Ahh, I see you're a man of **Kenja Values** as well...\n``{kenja_value}``")
