# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import discord
import json
import sys
import asyncio

from hifisuperstar.Bot import Bot
from hifisuperstar.cogs.Regex.RegexCog import RegexCog
from hifisuperstar.cogs.SelectableRoles.SelectableRolesCog import SelectableRolesCog
from hifisuperstar.cogs.UserJoin.UserJoinCog import UserJoinCog
from hifisuperstar.core.Server.Events import Events
from hifisuperstar.io.Logger import log_init
from hifisuperstar.cogs.Music.MusicCog import MusicCog
from hifisuperstar.cogs.Spotify.SpotifyCog import SpotifyCog
from hifisuperstar.cogs.AntiLoudmouth.AntiLoudmouthCog import AntiLoudmouthCog
from hifisuperstar.cogs.Jokes.JokesCog import JokesCog
from hifisuperstar.cogs.RandomPictures.RandomPicturesCog import RandomPicturesCog
from hifisuperstar.cogs.Kenja.KenjaCog import KenjaCog
from hifisuperstar.cogs.Acl.AclCog import AclCog
from hifisuperstar.cogs.ImageSearch.ImageSearchCog import ImageSearchCog
from hifisuperstar.cogs.VoiceRecorder.VoiceRecorderCog import VoiceRecorderCog
from hifisuperstar.cogs.Szperus.SzperusCog import SzperusCog
from hifisuperstar.io.UnbufferedOutput import UnbufferedOutput

# Disable output buffering
sys.stdout = UnbufferedOutput(sys.stdout)
sys.stdout.reconfigure(encoding='utf-8')

# Read configuration
config = {}
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.loads(f.read())

# Configure the Discord client
client = Bot(intents=(discord.Intents.all()))

# Setup logging
log_init()

# Setup events
@client.event
async def on_member_join(member):
    await Events.run_event('on_member_join', member=member)

@client.event
async def on_reaction_add(reaction, member):
    await Events.run_event('on_reaction_add', reaction=reaction, member=member)

@client.event
async def on_message(message):
    await Events.run_event('on_message', message=message)

@client.event
async def on_voice_state_update(member, prev, cur):
    await Events.run_event('on_voice_state_update', member=member, prev=prev, cur=cur)


# Add all cogs
if len(config['Bot']['Enabled_Cogs']) == 0:
    print('No cogs have been enabled. Please enable at least 1 cog in the config.json file.')
    sys.exit(1)

if 'Music' in config['Bot']['Enabled_Cogs']:
    client.add_cog(MusicCog(config))

if 'Spotify' in config['Bot']['Enabled_Cogs']:
    client.add_cog(SpotifyCog(config))

if 'AntiLoudmouth' in config['Bot']['Enabled_Cogs']:
    client.add_cog(AntiLoudmouthCog(config, client))

if 'Jokes' in config['Bot']['Enabled_Cogs']:
    client.add_cog(JokesCog(config))

if 'RandomPictures' in config['Bot']['Enabled_Cogs']:
    client.add_cog(RandomPicturesCog(config))

if 'Kenja' in config['Bot']['Enabled_Cogs']:
    client.add_cog(KenjaCog(config))

if 'Acl' in config['Bot']['Enabled_Cogs']:
    client.add_cog(AclCog(config))

if 'ImageSearch' in config['Bot']['Enabled_Cogs']:
    client.add_cog(ImageSearchCog(config))

if 'VoiceRecorder' in config['Bot']['Enabled_Cogs']:
    client.add_cog(VoiceRecorderCog(config))

if 'Regex' in config['Bot']['Enabled_Cogs']:
    client.add_cog(RegexCog(config))

if 'UserJoin' in config['Bot']['Enabled_Cogs']:
    client.add_cog(UserJoinCog(config))

if 'SelectableRoles' in config['Bot']['Enabled_Cogs']:
    client.add_cog(SelectableRolesCog(config))

if 'Szperus' in config['Bot']['Enabled_Cogs']:
    client.add_cog(SzperusCog(config))

# Run the client
client.run(config['Bot']['Token'])
