# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord


async def respond(interaction: discord.Interaction, content=None, **kwargs):
    if not interaction.response.is_done():
        await interaction.response.send_message(content, **kwargs)
    else:
        await interaction.followup.send(content, **kwargs)


async def check_server(interaction: discord.Interaction):
    if interaction.guild is None:
        await respond(interaction, 'ERROR: You need to message me from a server channel.')
        return False

    return True


async def join_voice(interaction: discord.Interaction):
    if interaction.user.voice is None:
        await respond(interaction, 'ERROR: You need to join a voice channel to do that.')
        return False

    channel = interaction.user.voice.channel
    if interaction.guild.voice_client is None:
        await channel.connect()
    else:
        await interaction.guild.voice_client.move_to(channel)

    return True
