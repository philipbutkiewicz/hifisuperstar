# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#
from hifisuperstar.io.Logger import warn
from hifisuperstar.io.Resources import load_resource
from hifisuperstar.io.Resources import save_resource


class Acl:

    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.rules = load_resource('acl', self.guild_id)

    def save_rules(self):
        save_resource('acl', self.guild_id, self.rules)

    def clear(self):
        self.rules = {}

    def set_rule(self, rule, allowed, resource_id):
        if not str(resource_id) in self.rules:
            self.rules[str(resource_id)] = {}

        self.rules[str(resource_id)][str(rule)] = allowed

    def toggle_admin_mode(self):
        if 'ADMIN_MODE' not in self.rules:
            self.rules['ADMIN_MODE'] = True
        else:
            self.rules['ADMIN_MODE'] = True if not self.rules['ADMIN_MODE'] else False

        return self.rules['ADMIN_MODE']

    def is_allowed(self, rule, resource_id, default=False):
        if 'ADMIN_MODE' in self.rules and self.rules['ADMIN_MODE']:
            return False

        if not str(resource_id) in self.rules:
            return default

        if rule not in self.rules[str(resource_id)]:
            return default

        return self.rules[str(resource_id)][str(rule)] == '1'

    async def check_and_fail(self, rule, ctx):
        if not self.is_allowed(rule, ctx.author.id, True):
            warn(self, f"The user {ctx.author.id} does not have permission to do that", ctx.guild)
            await ctx.respond('Sorry, you are not permitted to do that.')
            return False

        return True
