#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2022 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#
import discord
from discord.ui import Item, Select

from hifisuperstar.io.Logger import error, info


class SelectableRolesView(discord.ui.View):

    def __init__(self, selectable_roles, ctx, *items: Item):
        super().__init__(*items, timeout=None)
        self.selectable_roles = selectable_roles
        self.ctx = ctx

        self.select = Select(
            options=self.generate_options(),
        )

        self.select.callback = self.select_callback

        self.add_item(self.select)

    def generate_options(self):
        options = []
        for selectable_role in self.selectable_roles[self.ctx.guild.id]:
            if discord.utils.get(self.ctx.guild.roles, name=selectable_role):
                options.append(
                    discord.SelectOption(
                        label=selectable_role,
                        description=self.selectable_roles[self.ctx.guild.id][selectable_role]['description']
                    )
                )

        return options

    async def select_callback(self, interaction):
        if len(self.select.values) < 1:
            error(self, 'Invalid role selection')
            return False

        role = self.select.values[0]

        info(self, f"Role selected as '{role}' for {interaction.user}", self.ctx.guild)

        info(self, f"Replying with interaction for {interaction.user}", self.ctx.guild)
        self.select.disabled = True

        await interaction.response.edit_message(
            content=f"Role '{role}' selected, it will be applied momentarily!",
            view=self
        )

        info(self, f"Removing existing selectable roles for {interaction.user}", self.ctx.guild)
        for selectable_role in self.selectable_roles[self.ctx.guild.id]:
            await self.ctx.author.remove_roles(discord.utils.get(self.ctx.guild.roles, name=selectable_role))

        info(self, f"Adding role '{role}' for {interaction.user}", self.ctx.guild)
        await self.ctx.author.add_roles(discord.utils.get(self.ctx.guild.roles, name=role))
