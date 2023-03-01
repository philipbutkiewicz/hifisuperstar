# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

async def check_server(ctx):
    print(ctx)
    if ctx.guild is None:
        await ctx.respond('ERROR: You need to message me from a server channel.')
        return False

    return True


async def join_voice(ctx):
    if ctx.author.voice is None:
        await ctx.respond('ERROR: You need to join a voice channel to do that.')
        return False

    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    else:
        await ctx.voice_client.move_to(channel)

    return True
