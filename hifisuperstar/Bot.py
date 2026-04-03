import asyncio
import discord
from discord.ext import commands


class Bot(commands.Bot):

    def __init__(self, **options):
        self.exposed_loop = None
        self._staged_cogs = []
        super().__init__(command_prefix='!', intents=options.pop('intents', discord.Intents.all()), **options)

    def stage_cog(self, cog):
        """Queue a cog to be registered during setup_hook (required because add_cog is async)."""
        self._staged_cogs.append(cog)

    async def setup_hook(self):
        for cog in self._staged_cogs:
            await self.add_cog(cog)
        await self.tree.sync()

    async def on_ready(self):
        self.exposed_loop = asyncio.get_running_loop()
