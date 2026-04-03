# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
from discord import app_commands
from discord.ext import commands
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import error
from hifisuperstar.core.Acl.Acl import Acl
from hifisuperstar.core.Server.Server import check_server, respond


class AclCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.admin_mode = False

    @app_commands.command(name='set_rule', description='Sets an ACL rule')
    @app_commands.checks.has_role('Admin')
    async def set_rule(self, interaction: discord.Interaction, rule: str, allowed: str, user: discord.Member):
        info(self, 'ACL rule request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not user or not user.id:
            error(self, f"Unable to find user {user}", interaction.guild)
            return await respond(interaction, 'User not found.')

        info(self, f"Setting rule {rule} for {user.id}", interaction.guild)

        acl = Acl(interaction.guild.id)
        acl.set_rule(rule, allowed, user.id)
        acl.save_rules()

        await respond(interaction, 'Rule has been set.')

    @app_commands.command(name='clear_rules', description='Clears all ACL rules')
    @app_commands.checks.has_role('Admin')
    async def clear_rules(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        info(self, f"Clearing rules", interaction.guild)

        acl = Acl(interaction.guild.id)
        acl.clear()
        acl.save_rules()

        await respond(interaction, 'Rules have been cleared.')

    @app_commands.command(name='admin_mode', description='Toggles admin mode')
    @app_commands.checks.has_role('Admin')
    async def admin_mode(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        info(self, f"Toggling admin mode", interaction.guild)

        acl = Acl(interaction.guild.id)
        admin_mode = acl.toggle_admin_mode()
        acl.save_rules()

        await respond(interaction, f"Admin mode has been toggled {'on' if admin_mode else 'off'}")
