# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import glob
import os
import random
import discord
from discord import app_commands
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import error
from hifisuperstar.core.Server.Server import check_server, respond
from discord.ext import commands


class RandomPicturesCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.pictures = self.load_pictures()

    def load_pictures(self):
        if not os.path.exists('res/pictures'):
            raise Exception('Failed to find the picture database.')

        picture_types = self.config['RandomPicturesCog']['Enabled_Picture_Types']
        allowed_file_types = self.config['RandomPicturesCog']['Allowed_File_Types']

        pictures = {}
        for picture_type in picture_types:
            info(self, f"Loading '{picture_type}' pictures...")

            picture_type_list = []
            for file_type in allowed_file_types:
                picture_type_list.extend(glob.glob(f"res/pictures/{picture_type}s/*.{file_type}"))

            pictures[picture_type] = picture_type_list

            info(self, f"Loaded {len(picture_type_list)} of '{picture_type}' pictures!")

        return pictures

    async def send_picture(self, picture_type, interaction: discord.Interaction):
        info(self, 'Random picture request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        info(self, f"Picture request of the '{picture_type}' type", interaction.guild)

        if picture_type not in self.pictures or len(self.pictures[picture_type]) == 0:
            return await respond(interaction, f"Sorry, there are no {picture_type} pictures available. :(")

        with open(random.choice(self.pictures[picture_type]), 'rb') as f:
            return await respond(interaction, f"Here is a picture of a {picture_type} just for you!", file=discord.File(f))

    @app_commands.command(name='cat', description='Random cat picture')
    async def cat(self, interaction: discord.Interaction):
        await self.send_picture('cat', interaction)

    @app_commands.command(name='pug', description='Random pug picture')
    async def pug(self, interaction: discord.Interaction):
        await self.send_picture('pug', interaction)
