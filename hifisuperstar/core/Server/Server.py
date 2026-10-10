#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import asyncio

import discord

from hifisuperstar.io.Logger import error

_voice_locks = {}


async def connect_voice(channel):
    lock = _voice_locks.setdefault(channel.guild.id, asyncio.Lock())
    async with lock:
        voice = channel.guild.voice_client
        if voice is not None and not voice.is_connected():
            await voice.disconnect(force=True)
            voice = None
        if voice is None:
            return await channel.connect(timeout=30, reconnect=True)
        if voice.channel != channel:
            await voice.move_to(channel)
        return voice


async def respond(interaction: discord.Interaction, content=None, **kwargs):
    if not interaction.response.is_done():
        await interaction.response.send_message(content, **kwargs)
    else:
        await interaction.followup.send(content, **kwargs)


async def respond_or_send(interaction: discord.Interaction, content=None, **kwargs):
    """Like respond(), but falls back to a plain channel message once the interaction token has expired
    (long-running commands outlive the 15 minute followup window)."""
    try:
        return await respond(interaction, content, **kwargs)
    except discord.HTTPException as exc:
        error(None, f"Interaction response failed ({exc}), using channel message")
        if interaction.channel is None:
            return None
        kwargs.pop("ephemeral", None)
        return await interaction.channel.send(content, **kwargs)


async def defer(interaction: discord.Interaction):
    if not interaction.response.is_done():
        await interaction.response.defer()


async def check_server(interaction: discord.Interaction):
    if interaction.guild is None:
        await respond(
            interaction, "ERROR: You need to message me from a server channel."
        )
        return False

    return True


async def join_voice(interaction: discord.Interaction):
    if interaction.user.voice is None:
        await respond(
            interaction, "ERROR: You need to join a voice channel to do that."
        )
        return False

    channel = interaction.user.voice.channel
    current = interaction.guild.voice_client
    if (
        current is not None
        and current.is_connected()
        and current.channel != channel
        and (current.is_playing() or current.is_paused())
    ):
        await respond(
            interaction,
            "ERROR: I'm already playing music in another voice channel.",
        )
        return False

    try:
        voice = await connect_voice(channel)
        if not voice.is_connected():
            raise discord.ClientException("Voice connection did not complete")
    except (TimeoutError, discord.DiscordException, OSError) as exc:
        error(None, f"Could not join voice: {exc}", interaction.guild)
        await respond(
            interaction, "ERROR: Could not connect to voice. Please try again."
        )
        return False

    return True
