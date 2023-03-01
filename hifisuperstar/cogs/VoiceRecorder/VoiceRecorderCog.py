#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import os
from datetime import datetime
from discord.sinks import OGGSink
from discord.utils import get
from hifisuperstar.io.Logger import info, error
from hifisuperstar.core.Server.Server import check_server, join_voice
from discord.ext import commands


class VoiceRecorderCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.sink = None

    async def after_recording(self, *argv):
        ctx = argv[1]

        info(self, 'Recording was stopped', ctx.guild)

        audio_path = os.path.join('storage', str(ctx.guild.id))
        if not os.path.exists(audio_path):
            os.mkdir(audio_path)

        index = 0
        for audio in self.sink.get_all_audio():
            audio_path = os.path.join(audio_path, f"recording"
                                                  f"-{datetime.now().strftime('%d-%m-%Y %H.%M.%S')}-{index}.ogg")

            info(self, f"Writing audio to '{audio_path}'...")
            with open(audio_path, 'wb') as outfile:
                outfile.write(audio.read())

            index += 1

        self.sink = None

        await ctx.respond('Voice recording data saved.')

    @commands.slash_command(description='Starts recording voice channel audio')
    @commands.has_role('Admin')
    async def start_recording(self, ctx):
        info(self, 'Start voice recording request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await join_voice(ctx):
            return False

        if self.sink is not None:
            return ctx.respond('ERROR: Recording already in progress!')

        voice = get(ctx.bot.voice_clients, guild=ctx.guild)

        info(self, 'Creating a new sink and starting recording', ctx.guild)
        try:
            self.sink = OGGSink()
            voice.start_recording(self.sink, self.after_recording, ctx)
        except Exception as e:
            error(self, f"Starting recording failed: {e}", ctx.guild)
            return await ctx.respond('ERROR: Failed to start recording')

        await ctx.respond('Recording started!')

    @commands.slash_command(description='Stops recording voice channel audio')
    @commands.has_role('Admin')
    async def stop_recording(self, ctx):
        info(self, 'Stop voice recording request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await join_voice(ctx):
            return False

        voice = get(ctx.bot.voice_clients, guild=ctx.guild)

        info(self, 'Stopping recording...', ctx.guild)
        try:
            voice.stop_recording()
        except Exception as e:
            error(self, f"Stopping recording failed: {e}", ctx.guild)
            return await ctx.respond('ERROR: Failed to stop recording')

        await ctx.respond('Recording stopped!')
