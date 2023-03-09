#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import asyncio
import threading
from discord.utils import get
from hifisuperstar.cogs.AntiLoudmouth.Dsp.Rms import get_chunk_log_rms
from hifisuperstar.cogs.AntiLoudmouth.Sinks.RawSink import RawSink
from hifisuperstar.io.Logger import info, error
from hifisuperstar.core.Server.Server import check_server, join_voice
from discord.ext import commands


class AntiLoudmouthCog(commands.Cog):
    def __init__(self, config, client):
        info(self, 'Registered')
        self.config = config
        self.client = client
        self.sink = None


    async def loudmouth_detected(self, user_id, rms, ctx):
        user = await self.client.fetch_user(user_id)

        if user.name == 'Hifi Superstar':
            return False
        
        if not user:
            error(self, f'Failed to fetch user with ID {user_id}!', ctx.guild)
            return False
        
        info(self, f'Messaging user that they are too loud ({rms} db on average): {user.name}', ctx.guild)
        
        return await user.send(f'You\'re being way too loud ({rms} db on average) - keep it down!')


    def loudmouth_detected_thread(self, user_id, rms, ctx):
        asyncio.run_coroutine_threadsafe(self.loudmouth_detected(user_id, rms, ctx), self.client.exposed_loop)


    def audio_received(self, user_id, data, ctx):
        rms = get_chunk_log_rms(data)
        if rms > float(self.config['AntiLoudmouthCog']['DecibelsRMSThreshold']):
            threading.Thread(target=self.loudmouth_detected_thread, args=[user_id, rms, ctx]).start()



    async def after_recording(self, *argv):
        ctx = argv[1]

        info(self, 'Monitoring stopped', ctx.guild)

        self.sink = None


    @commands.slash_command(description='Starts monitoring voice channel audio for loudmouths')
    @commands.has_role('Admin')
    async def start_monitoring(self, ctx):
        info(self, 'Start voice monitoring request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await join_voice(ctx):
            return False

        if self.sink is not None:
            return ctx.respond('ERROR: Monitoring already in progress!')

        voice = get(ctx.bot.voice_clients, guild=ctx.guild)

        info(self, 'Creating a new sink and starting monitoring', ctx.guild)
        try:
            self.sink = RawSink()
            self.sink.ctx = ctx
            self.sink.audio_received = self.audio_received
            voice.start_recording(self.sink, self.after_recording, ctx)
        except Exception as e:
            error(self, f"Starting monitoring failed: {e}", ctx.guild)
            return await ctx.respond('ERROR: Failed to start monitoring')

        await ctx.respond('Monitoring started!')


    @commands.slash_command(description='Stops monitoring voice channel audio for loudmouths')
    @commands.has_role('Admin')
    async def stop_monitoring(self, ctx):
        info(self, 'Stop voice monitoring request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await join_voice(ctx):
            return False

        voice = get(ctx.bot.voice_clients, guild=ctx.guild)

        info(self, 'Stopping monitoring...', ctx.guild)
        try:
            voice.stop_recording()
        except Exception as e:
            error(self, f"Stopping monitoring failed: {e}", ctx.guild)
            return await ctx.respond('ERROR: Failed to stop monitoring')

        await ctx.respond('Monitoring stopped!')
