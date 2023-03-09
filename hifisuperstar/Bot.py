import asyncio
from typing import Any, Optional
import discord

class Bot(discord.Bot):

    def __init__(self, *, loop: Optional[asyncio.AbstractEventLoop] = None, **options: Any):
        self.exposed_loop = None
        super().__init__(loop=loop, **options)

    async def on_ready(self):
        self.exposed_loop = asyncio.get_running_loop() 
