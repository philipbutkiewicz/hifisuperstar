#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
from discord import app_commands
from discord.ext import commands

from hifisuperstar.core.Server.Events import Events
from hifisuperstar.core.Server.Server import check_server, respond
from hifisuperstar.io.Logger import error, warn
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Resources import load_resource, save_resource


class SelectableRolesCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.selectable_roles = {}
        self.message_ids = {}
        self.setup_events()

    def setup_events(self):
        Events.add_event('on_reaction_add', self.on_reaction_add)
        return

    def load_selectable_roles(self, guild_id):
        self.selectable_roles[guild_id] = load_resource('selectableroles', guild_id)

    def save_selectable_roles(self, guild_id):
        save_resource('selectableroles', guild_id, self.selectable_roles[guild_id])

    def load_message_ids(self, guild_id):
        self.selectable_roles[guild_id] = load_resource('messageids', guild_id)

    def save_message_ids(self, guild_id):
        save_resource('messageids', guild_id, self.message_ids[guild_id])

    def load_selected_list(self, guild_id, list_name):
        if not list_name in self.selectable_roles[guild_id]:
            self.selectable_roles[guild_id]['default' if list_name is None else list_name] = {}
        
        return self.selectable_roles[guild_id]['default' if list_name is None else list_name]

    async def on_reaction_add(self, reaction, member):
        message = reaction.message

        if not message.author.bot:
            warn(self, 'Cannot react to non-bot messages')
            return False

        if member.bot:
            warn(self, 'Cannot react to self')
            return False

        if not message.guild or not message.guild.id:
            warn(self, f"Not a server reaction: {reaction}")
            return False

        self.load_message_ids(message.guild.id)
        
        if not message.id in self.message_ids[message.guild.id]:
            warn(self, f"Message ID {message.id} is not valid for reactions")
            return False
        
        selected_list = self.load_selected_list(message.guild.id, self.message_ids[message.guild.id][message.id])
        role = None
        for selectable_role in selected_list:
            if selectable_role['emoji'] == reaction.emoji.name:
                role = selectable_role
                break

        info(self, f"Role selected as '{role}' for {member}", message.guild)

        info(self, f"Removing existing selectable roles for {member}", message.guild)
        for selectable_role in selected_list:
            await member.remove_roles(discord.utils.get(message.guild.roles, name=selectable_role))

        info(self, f"Adding role '{role}' for {member}", message.guild)
        await member.add_roles(discord.utils.get(message.guild.roles, name=role))

    @app_commands.command(name='add_selectable_role', description='Adds a user selectable role')
    @app_commands.checks.has_role('Admin')
    async def add_selectable_role(self, interaction: discord.Interaction, role: str, emoji: str = "👍", list_name: str = None):
        info(self, 'Add selectable role request', interaction.guild)

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if interaction.guild.id not in self.selectable_roles:
            self.load_selectable_roles(interaction.guild.id)
        
        selected_list = self.load_selected_list(interaction.guild.id, list_name)

        if not discord.utils.get(interaction.guild.roles, name=role):
            error(self, f"Role {role} does not exist")
            return await respond(interaction, f"Role '{role}' does not exist!")

        selected_list[role] = {
            'emoji': emoji
        }

        self.save_selectable_roles(interaction.guild.id)

        await respond(interaction, f"Role '{role}' has been added to list '{list_name}'.")

    @app_commands.command(name='remove_selectable_role', description='Removes a user selectable role')
    @app_commands.checks.has_role('Admin')
    async def remove_selectable_role(self, interaction: discord.Interaction, role: str, list_name: str = None):
        info(self, 'Remove selectable role request', interaction.guild)

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if interaction.guild.id not in self.selectable_roles:
            self.load_selectable_roles(interaction.guild.id)

        selected_list = self.load_selected_list(interaction.guild.id, list_name)

        if role not in selected_list:
            error(self, f"Role {role} does not exist in list {selected_list}")
            return await respond(interaction, f"Role '{role}' does not exist in list '{selected_list}'!")

        del selected_list[role]

        self.save_selectable_roles(interaction.guild.id)

        await respond(interaction, f"Role '{role}' has been removed from list '{selected_list}'.")

    @app_commands.command(name='selectable_roles', description='Creates a selectable roles message')
    @app_commands.checks.has_role('Admin')
    async def selectable_roles(self, interaction: discord.Interaction, message: str = None, list_name: str = None):
        info(self, 'Selectable role request', interaction.guild)

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if interaction.guild.id not in self.selectable_roles:
            self.load_selectable_roles(interaction.guild.id)

        selected_list = self.load_selected_list(interaction.guild.id, list_name)

        await respond(interaction, 'Choose your role' if message is None else message)
        msg = await interaction.original_response()
        for selectable_role in selected_list:
            await msg.add_reaction(selected_list[selectable_role]['emoji'])
        
        self.load_message_ids(interaction.guild.id)
        self.message_ids[interaction.guild.id][msg.id] = 'default' if list_name is None else list_name
        self.save_message_ids(interaction.guild.id)
