# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
from discord.ext import commands
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import error
from hifisuperstar.core.Acl.Acl import Acl
from hifisuperstar.core.Server.Server import check_server


class AclCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.admin_mode = False

    @commands.slash_command(description='Sets an ACL rule')
    @commands.has_role('Admin')
    async def set_rule(self, ctx, rule, allowed, user: discord.Member):
        info(self, 'ACL rule request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not user or not user.id:
            error(self, f"Unable to find user {user}", ctx.guild)
            return await ctx.respond('User not found.')

        info(self, f"Setting rule {rule} for {user.id}", ctx.guild)

        acl = Acl(ctx.guild.id)
        acl.set_rule(rule, allowed, user.id)
        acl.save_rules()

        await ctx.respond('Rule has been set.')

    @commands.slash_command(description='Clears all ACL rules')
    @commands.has_role('Admin')
    async def clear_rules(self, ctx):
        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        info(self, f"Clearing rules", ctx.guild)

        acl = Acl(ctx.guild.id)
        acl.clear()
        acl.save_rules()

        await ctx.respond('Rules have been cleared.')

    @commands.slash_command(description='Toggles admin mode')
    @commands.has_role('Admin')
    async def admin_mode(self, ctx):
        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        info(self, f"Toggling admin mode", ctx.guild)

        acl = Acl(ctx.guild.id)
        admin_mode = acl.toggle_admin_mode()
        acl.save_rules()

        await ctx.respond(f"Admin mode has been toggled {'on' if admin_mode else 'off'}")
