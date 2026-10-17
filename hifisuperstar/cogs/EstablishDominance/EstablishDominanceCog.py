#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
from discord import app_commands
from discord.ext import commands

from hifisuperstar.core.Server.Events import Events
from hifisuperstar.core.Server.Server import check_server, respond
from hifisuperstar.io.GuildConfig import get_guild_config
from hifisuperstar.io.Logger import error, info
from hifisuperstar.io.Resources import load_resource, save_resource


def is_blocked_bot(member, blocked_bots):
    """True for a bot account matching an entry of Blocked_Bots (by "Id", or by "Name" + optional "Discriminator")."""
    if not member.bot:
        return False

    for entry in blocked_bots:
        if entry.get("Id") and str(member.id) == str(entry["Id"]):
            return True

        name = entry.get("Name")
        if name and member.name.lower() == str(name).lower():
            discriminator = entry.get("Discriminator")
            # Accounts migrated to the new username system have discriminator "0" and match by name only
            if (
                discriminator
                and member.discriminator not in ("0", "", None)
                and member.discriminator != str(discriminator)
            ):
                continue
            return True

    return False


class EstablishDominanceCog(commands.Cog):
    """Disconnects rival music bots from voice channels as soon as they show up."""

    def __init__(self, config, bot):
        info(self, "Registered")
        self.config = config
        self.bot = bot
        self.enabled_guilds = {}
        Events.add_event("on_voice_state_update", self.on_voice_state_update)

    def is_enabled(self, guild_id):
        # Dominance is established by default, /establish_dominance_toggle turns it off per server
        if guild_id not in self.enabled_guilds:
            settings = load_resource("establishdominance", guild_id)
            self.enabled_guilds[guild_id] = bool(settings.get("enabled", True))

        return self.enabled_guilds[guild_id]

    def get_blocked_bots(self, guild_id):
        settings = get_guild_config(self.config, "EstablishDominanceCog", guild_id)
        # Nobody is blocked until bots are listed in the config
        return settings.get("Blocked_Bots") or []

    async def kick_from_voice(self, member):
        info(
            self,
            f"Disconnecting blocked bot {member} from voice channel '{member.voice.channel}'",
            member.guild,
        )
        try:
            await member.move_to(None, reason="Blocked bot (EstablishDominanceCog)")
        except discord.Forbidden:
            error(
                self,
                f"Missing the Move Members permission to disconnect {member}",
                member.guild,
            )
        except discord.HTTPException as exc:
            error(self, f"Could not disconnect {member}: {exc}", member.guild)

    async def kick_blocked_bots_in(self, guild):
        blocked_bots = self.get_blocked_bots(guild.id)
        for channel in guild.voice_channels:
            for member in list(channel.members):
                if is_blocked_bot(member, blocked_bots):
                    await self.kick_from_voice(member)

    async def on_voice_state_update(self, member, prev, cur):
        # Only react to joining or switching channels, not to mute/deafen changes
        if cur.channel is None or cur.channel == prev.channel:
            return

        if not self.is_enabled(member.guild.id):
            return

        if is_blocked_bot(member, self.get_blocked_bots(member.guild.id)):
            await self.kick_from_voice(member)

    @commands.Cog.listener()
    async def on_ready(self):
        # Bots that were already in voice before this bot started never trigger a voice state event
        for guild in self.bot.guilds:
            if self.is_enabled(guild.id):
                await self.kick_blocked_bots_in(guild)

    @app_commands.command(
        name="establish_dominance_toggle",
        description="Toggles disconnecting rival music bots from voice channels",
    )
    @app_commands.checks.has_role("Admin")
    async def establish_dominance_toggle(self, interaction: discord.Interaction):
        info(self, "Establish dominance toggle request")

        if not await check_server(interaction):
            error(self, "Server verification failed")
            return False

        enabled = not self.is_enabled(interaction.guild.id)
        self.enabled_guilds[interaction.guild.id] = enabled
        save_resource("establishdominance", interaction.guild.id, {"enabled": enabled})

        info(
            self,
            f"Establishing dominance is now {'on' if enabled else 'off'}",
            interaction.guild,
        )
        await respond(
            interaction,
            "Dominance is being established. 😎"
            if enabled
            else "Standing down. Rival bots may stay in voice channels again.",
        )

        if enabled:
            await self.kick_blocked_bots_in(interaction.guild)
