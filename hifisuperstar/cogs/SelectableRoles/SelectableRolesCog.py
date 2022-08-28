#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2022 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
from discord.ui import Select
from discord.ui import View
from discord.ext import commands

from hifisuperstar.cogs.SelectableRoles.SelectableRolesView import SelectableRolesView
from hifisuperstar.core.Server.Events import Events
from hifisuperstar.core.Server.Server import check_server
from hifisuperstar.io.Logger import error, warn
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Resources import load_resource, save_resource


class SelectableRolesCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.selectable_roles = {}

    def load_selectable_roles(self, guild_id):
        self.selectable_roles[guild_id] = load_resource('selectableroles', guild_id)

    def save_selectable_roles(self, guild_id):
        save_resource('selectableroles', guild_id, self.selectable_roles[guild_id])

    @commands.slash_command(description='Adds a user selectable role')
    @commands.has_role('Admin')
    async def add_selectable_role(self, ctx, role, description=None):
        info(self, 'Add selectable role request', ctx.guild)

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if ctx.guild.id not in self.selectable_roles:
            self.load_selectable_roles(ctx.guild.id)

        if not discord.utils.get(ctx.guild.roles, name=role):
            error(self, f"Role {role} does not exist")
            return await ctx.respond(f"Role '{role}' does not exist!")

        self.selectable_roles[ctx.guild.id][role] = {'description': description}

        self.save_selectable_roles(ctx.guild.id)

        await ctx.respond(f"Role '{role}' has been added.")

    @commands.slash_command(description='Removes a user selectable role')
    @commands.has_role('Admin')
    async def remove_selectable_role(self, ctx, role):
        info(self, 'Remove selectable role request', ctx.guild)

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if ctx.guild.id not in self.selectable_roles:
            self.load_selectable_roles(ctx.guild.id)

        if role not in self.selectable_roles[ctx.guild.id]:
            error(self, f"Role {role} does not exist")
            return await ctx.respond(f"Role '{role}' does not exist!")

        del self.selectable_roles[ctx.guild.id][role]

        self.save_selectable_roles(ctx.guild.id)

        await ctx.respond(f"Role '{role}' has been removed.")

    @commands.slash_command(description='Allows the user to choose a user selectable role')
    async def selectable_roles(self, ctx):
        info(self, 'Selectable role request', ctx.guild)

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if ctx.guild.id not in self.selectable_roles:
            self.load_selectable_roles(ctx.guild.id)

        await ctx.author.send('Choose your role!', view=SelectableRolesView(self.selectable_roles, ctx))
        await ctx.respond('Check your DMs. :)')
