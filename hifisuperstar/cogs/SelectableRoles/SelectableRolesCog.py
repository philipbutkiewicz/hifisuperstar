#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
from discord import app_commands
from discord.ext import commands

from hifisuperstar.core.Server.Events import Events
from hifisuperstar.core.Server.Server import check_server, respond
from hifisuperstar.io.Logger import error, info, warn
from hifisuperstar.io.Resources import load_resource, save_resource


class SelectableRolesCog(commands.Cog):
    def __init__(self, config):
        info(self, "Registered")
        self.config = config
        self.selectable_roles = {}
        self.message_ids = {}
        self.setup_events()

    def setup_events(self):
        Events.add_event("on_raw_reaction_add", self.on_raw_reaction_add)

    def load_selectable_roles(self, guild_id):
        self.selectable_roles[guild_id] = load_resource("selectableroles", guild_id)

    def save_selectable_roles(self, guild_id):
        save_resource("selectableroles", guild_id, self.selectable_roles[guild_id])

    def load_message_ids(self, guild_id):
        self.message_ids[guild_id] = load_resource("messageids", guild_id)

    def save_message_ids(self, guild_id):
        save_resource("messageids", guild_id, self.message_ids[guild_id])

    def load_selected_list(self, guild_id, list_name):
        name = "default" if list_name is None else list_name
        if name not in self.selectable_roles[guild_id]:
            self.selectable_roles[guild_id][name] = {}

        return self.selectable_roles[guild_id][name]

    async def on_raw_reaction_add(self, payload):
        # Raw events also fire for messages that are not in the cache (e.g. after a restart)
        member = payload.member
        if member is None or member.bot or payload.guild_id is None:
            return False

        guild = member.guild
        self.load_message_ids(guild.id)

        message_id = str(payload.message_id)
        if message_id not in self.message_ids[guild.id]:
            return False

        self.load_selectable_roles(guild.id)
        selected_list = self.load_selected_list(
            guild.id, self.message_ids[guild.id][message_id]
        )
        role = None
        for selectable_role in selected_list:
            if selected_list[selectable_role]["emoji"] == payload.emoji.name:
                role = selectable_role
                break

        if role is None:
            return False

        new_role = discord.utils.get(guild.roles, name=role)
        if new_role is None:
            warn(self, f"Role '{role}' no longer exists", guild)
            return False

        info(self, f"Role selected as '{role}' for {member}", guild)

        old_roles = [
            existing
            for name in selected_list
            if name != role
            and (existing := discord.utils.get(member.roles, name=name)) is not None
        ]
        try:
            if old_roles:
                await member.remove_roles(*old_roles)
            await member.add_roles(new_role)
        except discord.HTTPException as exc:
            error(self, f"Could not update roles for {member}: {exc}", guild)
            return False

    @app_commands.command(
        name="add_selectable_role", description="Adds a user selectable role"
    )
    @app_commands.checks.has_role("Admin")
    async def add_selectable_role(
        self,
        interaction: discord.Interaction,
        role: str,
        emoji: str = "👍",
        list_name: str | None = None,
    ):
        info(self, "Add selectable role request", interaction.guild)

        if not await check_server(interaction):
            error(self, "Server verification failed")
            return False

        if interaction.guild.id not in self.selectable_roles:
            self.load_selectable_roles(interaction.guild.id)

        selected_list = self.load_selected_list(interaction.guild.id, list_name)

        if not discord.utils.get(interaction.guild.roles, name=role):
            error(self, f"Role {role} does not exist")
            return await respond(interaction, f"Role '{role}' does not exist!")

        selected_list[role] = {"emoji": emoji}

        self.save_selectable_roles(interaction.guild.id)

        await respond(
            interaction, f"Role '{role}' has been added to list '{list_name or 'default'}'."
        )

    @app_commands.command(
        name="remove_selectable_role", description="Removes a user selectable role"
    )
    @app_commands.checks.has_role("Admin")
    async def remove_selectable_role(
        self, interaction: discord.Interaction, role: str, list_name: str | None = None
    ):
        info(self, "Remove selectable role request", interaction.guild)

        if not await check_server(interaction):
            error(self, "Server verification failed")
            return False

        if interaction.guild.id not in self.selectable_roles:
            self.load_selectable_roles(interaction.guild.id)

        selected_list = self.load_selected_list(interaction.guild.id, list_name)

        if role not in selected_list:
            error(self, f"Role {role} does not exist in list {list_name or 'default'}")
            return await respond(
                interaction,
                f"Role '{role}' does not exist in list '{list_name or 'default'}'!",
            )

        del selected_list[role]

        self.save_selectable_roles(interaction.guild.id)

        await respond(
            interaction, f"Role '{role}' has been removed from list '{list_name or 'default'}'."
        )

    @app_commands.command(
        name="selectable_roles", description="Creates a selectable roles message"
    )
    @app_commands.checks.has_role("Admin")
    async def selectable_roles(
        self,
        interaction: discord.Interaction,
        message: str | None = None,
        list_name: str | None = None,
    ):
        info(self, "Selectable role request", interaction.guild)

        if not await check_server(interaction):
            error(self, "Server verification failed")
            return False

        if interaction.guild.id not in self.selectable_roles:
            self.load_selectable_roles(interaction.guild.id)

        selected_list = self.load_selected_list(interaction.guild.id, list_name)

        await respond(interaction, "Choose your role" if message is None else message)
        msg = await interaction.original_response()
        for selectable_role in selected_list:
            await msg.add_reaction(selected_list[selectable_role]["emoji"])

        self.load_message_ids(interaction.guild.id)
        self.message_ids[interaction.guild.id][str(msg.id)] = (
            "default" if list_name is None else list_name
        )
        self.save_message_ids(interaction.guild.id)
