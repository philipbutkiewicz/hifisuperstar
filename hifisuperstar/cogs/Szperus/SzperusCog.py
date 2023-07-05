#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#
from discord import Forbidden

from hifisuperstar.core.Server.Events import Events
from hifisuperstar.io.Logger import info, error
from discord.ext import commands

class SzperusCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.setup_events()

    def setup_events(self):
        Events.add_event('on_message', self.on_message)
        return

    async def on_message(self, message):
        info(self, f"Message received")

        if message.author.id == 263312826653736960 and not message.author.display_name == "Szperus":
            try:
                await message.author.edit(nick="Szperus")
            except Forbidden:
                error(self, f"Shit hit the fun, I don't care why.")
                pass
