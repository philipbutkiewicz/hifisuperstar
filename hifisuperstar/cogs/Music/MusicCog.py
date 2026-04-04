# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import re
import discord
import validators
from discord import app_commands
from hifisuperstar.core.Music.Player import Player
from hifisuperstar.core.Music.Playlist import Playlist
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import warn
from hifisuperstar.io.Logger import error
from hifisuperstar.io.Strings import allowed_chars_regex
from hifisuperstar.core.Acl.Acl import Acl
from hifisuperstar.core.Acl import Rule
from hifisuperstar.core.Server.Server import check_server
from hifisuperstar.core.Server.Server import join_voice
from hifisuperstar.core.Server.Server import respond
from discord.ext import commands


# noinspection DuplicatedCode
class MusicCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.players = {}

    async def get_player(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return None

        if str(interaction.guild.id) not in self.players:
            self.players[str(interaction.guild.id)] = Player(interaction, self.config)

        return self.players[str(interaction.guild.id)]

    @app_commands.command(name='play', description='Plays or queues media, YouTube links, YouTube search queries and direct media '
                                        'links are supported.')
    async def play(self, interaction: discord.Interaction, query: str = None):
        info(self, 'Playback request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_PLAY, interaction):
            return False

        info(self, f"Playback request{': ' + query if not query is None else ''}", interaction.guild)

        if not await join_voice(interaction):
            return False

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        await respond(interaction, 'Hold on, let me look that up...')
        track_info = player.queue_track(query)
        if not track_info:
            error(self, 'Failed to queue', interaction.guild)
            return await respond(interaction, f"ERROR: Failed to queue '{'the current playlist' if query is None else query}'")

        await respond(interaction, f"Queued '{track_info['title'] if not query is None else 'the current playlist'}'!")

    @app_commands.command(name='play_radio', description='Plays radio')
    async def play_radio(self, interaction: discord.Interaction, query: str = None):
        info(self, 'Radio playback request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_PLAY, interaction):
            return False

        info(self, f"Radio playback request{': ' + query if not query is None else ''}", interaction.guild)

        if not await join_voice(interaction):
            return False

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')
        
        await player.stop_track()
        player.get_playlist().clear()

        await respond(interaction, 'Hold on, let me look that up...')
        if not player.queue_radio():
            error(self, 'Failed to queue radio playback', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to queue radio playback')

        await respond(interaction, 'Queued radio playback!')

    @app_commands.command(name='playlist', description='This command can queue a YouTube playlist if supplied with a valid URL, '
                                        'or load a saved playlist')
    async def playlist(self, interaction: discord.Interaction, query: str):
        info(self, 'Playback (playlist) request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_QUEUE, interaction):
            return False

        info(self, f"Playback (playlist) request: '{query}'", interaction.guild)

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        player.stop_track()

        if not validators.url(query):
            if not re.match(allowed_chars_regex, query):
                warn(self, 'Invalid input', interaction.guild)
                return await respond(interaction, 'ERROR: Invalid format, only alphanumeric characters or URLs are allowed.')

        await respond(interaction, 'Go get yourself a coffee, this can take a while...')
        playlist_info = await player.queue_playlist(query)
        if not playlist_info:
            error(self, 'Failed to queue', interaction.guild)
            return await respond(interaction, f"ERROR: Failed to queue '{query}'")

        await respond(interaction, f"Queued {len(playlist_info)} items!")

    @app_commands.command(name='list_playlists', description='Lists available playlists')
    async def list_playlists(self, interaction: discord.Interaction):
        info(self, 'List playlists request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_LIST, interaction):
            return False

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        playlists = player.get_playlist().get_available_playlists()
        if not playlists:
            error(self, 'Failed to list playlists', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to list playlists')

        embed = discord.Embed(
            title='Available Playlists',
            description='\n'.join(f"`{i + 1}.` {name}" for i, name in enumerate(playlists)),
            color=discord.Color.blurple()
        )

        if self.config['Web']['Enabled']:
            embed.add_field(
                name='Web',
                value=f"[Browse playlists]({self.config['Web']['Base_Url']}/playlists/{str(interaction.guild.id)})",
                inline=False
            )

        await respond(interaction, embed=embed)

    @app_commands.command(name='playlist_preview', description='Previews the current playlist')
    async def playlist_preview(self, interaction: discord.Interaction, name: str):
        info(self, 'preview playlist request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_LIST, interaction):
            return False

        if not validators.url(name):
            if not re.match(allowed_chars_regex, name):
                warn(self, 'Invalid input', interaction.guild)
                return await respond(interaction, 'ERROR: Invalid format, only alphanumeric characters or URLs are allowed.')

        playlist = Playlist(interaction.guild.id, name)
        if not playlist.load_from_storage():
            return await respond(interaction, 'Could not find a playlist with that name.')

        if self.config['Web']['Enabled']:
            await respond(interaction,
                f"You can view the contents of this playlist here: "
                f"{self.config['Web']['Base_Url']}/playlists/{str(interaction.guild.id)}/{name}")

    # noinspection DuplicatedCode
    @app_commands.command(name='playlist_save', description='Saves the current playlist')
    async def playlist_save(self, interaction: discord.Interaction, name: str):
        info(self, 'Save playlist request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_SAVE, interaction):
            return False

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        if not validators.url(name):
            if not re.match(allowed_chars_regex, name):
                warn(self, 'Invalid input', interaction.guild)
                return await respond(interaction, 'ERROR: Invalid format, only alphanumeric characters or URLs are allowed.')

        await respond(interaction, 'Saving the playlist...')
        playlist = player.get_playlist()
        playlist.set_name(name)

        if not playlist.save():
            error(self, 'Failed to save the playlist', interaction.guild)
            return await respond(interaction, f"ERROR: Failed to save playlist '{name}'")

        await respond(interaction, 'Playlist saved!')

    @app_commands.command(name='playlist_delete', description='Deletes a playlist with a given name')
    @app_commands.checks.has_role('Admin')
    async def playlist_delete(self, interaction: discord.Interaction, name: str):
        info(self, 'Delete playlist request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_DELETE, interaction):
            return False

        if not validators.url(name):
            if not re.match(allowed_chars_regex, name):
                warn(self, 'Invalid input', interaction.guild)
                return await respond(interaction, 'ERROR: Invalid format, only alphanumeric characters or URLs are allowed.')

        playlist = Playlist(interaction.guild.id, name)
        if not playlist.load_from_storage():
            warn(self, 'Playlist not found', interaction.guild)
            return await respond(interaction, f"ERROR: Playlist '{name}' not found!")

        if not playlist.delete():
            error(self, 'Failed to delete the playlist', interaction.guild)
            return await respond(interaction, f"ERROR: Failed to delete playlist '{name}'")

        await respond(interaction, 'Playlist deleted!')

    @app_commands.command(name='stop', description='Stops playback')
    async def stop(self, interaction: discord.Interaction):
        info(self, 'Playback stop request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_STOP, interaction):
            return False

        info(self, 'Stopping playback', interaction.guild)

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        await player.stop_track()
        player.get_playlist().clear()

        await respond(interaction, 'Done!')

    @app_commands.command(name='skip', description='Skips current item in the playback queue')
    async def skip(self, interaction: discord.Interaction):
        info(self, 'Go to next request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_SKIP, interaction):
            return False

        info(self, 'Skipping a track', interaction.guild)

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        player.skip_track()

        await respond(interaction, 'Done!')

    @app_commands.command(name='jump_to_index', description='Skips to a specific index in the queue')
    async def jump_to_index(self, interaction: discord.Interaction, index: str):
        info(self, 'Go to index request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_SKIP, interaction):
            return False

        info(self, f"Jumping to playlist index {index}", interaction.guild)

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        playlist = player.get_playlist()

        index = int(index)
        if index < 1 or index > len(playlist.get_tracks()):
            warn(self, 'Invalid input', interaction.guild)
            await respond(interaction, f"ERROR: Invalid format, provide a value between 1 and {len(playlist.get_tracks())}")
            return False

        player.skip_track_to_index(index - 1)

        await respond(interaction, 'Done!')

    @app_commands.command(name='prev', description='Goes back to the previous item in the playback queue')
    async def prev(self, interaction: discord.Interaction):
        info(self, 'Go to previous request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_SKIP, interaction):
            return False

        info(self, 'Going to a previous a track', interaction.guild)

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        player.prev_track()

        await respond(interaction, 'Done!')

    @app_commands.command(name='queue', description='Lists all items in the playback queue')
    async def queue(self, interaction: discord.Interaction):
        info(self, 'List queue items request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_QUEUE, interaction):
            return False

        info(self, 'Displaying the queue', interaction.guild)

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        display_queue_items = int(self.config['MusicCog']['Display_Queue_Items'])
        if display_queue_items < 10:
            warn(self, 'Queue misconfigured', interaction.guild)
            return await respond(interaction, 'ERROR: Queue misconfigured')

        playlist = player.get_playlist()
        queue = playlist.get_tracks()
        current_track = playlist.get_current_track()

        if len(queue) == 0:
            return await respond(interaction, 'ERROR: There is nothing in the queue')

        min_items = playlist.get_current_track_index() - (display_queue_items / 2) \
            if len(queue) > display_queue_items else playlist.get_current_track_index()
        max_items = playlist.get_current_track_index() + (display_queue_items / 2) \
            if playlist.get_current_track_index() + (display_queue_items / 2) < len(queue) else len(queue)

        lines = []
        for i in range(int(min_items), int(max_items)):
            is_current = current_track['id'] == queue[i]['id'] if current_track else False
            number = queue.index(queue[i]) + 1
            title = queue[i]['title']
            url = queue[i].get('url')
            track_label = f"[{title}]({url})" if url else title
            prefix = '▶ ' if is_current else f"`{number}.`  "
            lines.append(f"{prefix}{track_label}")

        embed = discord.Embed(
            title='Queue',
            description='\n'.join(lines),
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Showing {int(max_items) - int(min_items)} of {len(queue)} track(s)")

        await respond(interaction, embed=embed)

    @app_commands.command(name='top_tracks', description='Shows the most played tracks (in descending order)')
    async def top_tracks(self, interaction: discord.Interaction):
        info(self, 'List top tracks request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_TOP_TRACKS, interaction):
            return False

        info(self, 'Displaying top tracks', interaction.guild)

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        display_num_top_tracks = int(self.config['MusicCog']['Display_Num_Top_Tracks'])
        if display_num_top_tracks == 0:
            warn(self, 'Top tracks misconfigured', interaction.guild)
            return await respond(interaction, 'ERROR: Top tracks misconfigured')

        tracks = player.get_play_counter().get_all_counts()
        if len(tracks) == 0:
            return await respond(interaction, 'ERROR: Not enough top tracks to display')

        tracks_keys = list(tracks.keys())

        if display_num_top_tracks > len(tracks):
            display_num_top_tracks = len(tracks)

        lines = []
        for i in range(0, display_num_top_tracks):
            track = tracks[tracks_keys[i]]
            url = track.get('url')
            track_label = f"[{track['title']}]({url})" if url else track['title']
            lines.append(f"`{i + 1}.` {track_label} — **{track['count']}** play{'s' if track['count'] != 1 else ''}")

        embed = discord.Embed(
            title='Top Tracks',
            description='\n'.join(lines),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Showing top {display_num_top_tracks} track(s)")

        await respond(interaction, embed=embed)

    @app_commands.command(name='volume', description='Sets playback volume to a provided value between 0 and 1.0')
    async def volume(self, interaction: discord.Interaction, volume: str):
        info(self, 'Volume change request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_SET_VOLUME, interaction):
            return False

        info(self, 'Setting volume', interaction.guild)

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        try:
            volume = float(volume)
        except ValueError:
            warn(self, 'Invalid input', interaction.guild)
            return await respond(interaction, 'ERROR: Invalid format, not a float number')

        if volume < 0 or volume > 1:
            warn(self, 'Invalid input', interaction.guild)
            return await respond(interaction, 'ERROR: Invalid format, provide a value between 0 and 1.0')

        if player.set_volume(volume):
            warn(self, 'Invalid input', interaction.guild)
            return await respond(interaction, f"Volume is now set at {volume * 100}%")

        await respond(interaction, 'ERROR: Failed setting volume')

    @app_commands.command(name='repeat', description='Toggles repeat mode on or off')
    async def repeat(self, interaction: discord.Interaction):
        info(self, 'Repeat mode change request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_SET_REPEAT, interaction):
            return False

        info(self, 'Toggling repeat mode', interaction.guild)

        player = await self.get_player(interaction)
        if not player:
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        repeat = player.set_repeat()

        await respond(interaction, f"Repeat is now {'on' if repeat else 'off'}")

    @app_commands.command(name='repeat_all', description='Toggles repeat all mode on or off')
    async def repeat_all(self, interaction: discord.Interaction):
        info(self, 'Repeat all mode change request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_SET_REPEAT, interaction):
            return False

        info(self, 'Toggling repeat all mode', interaction.guild)

        player = await self.get_player(interaction)
        if not player:
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        repeat = player.set_repeat_all()

        await respond(interaction, f"Repeat is now {'on' if repeat else 'off'}")
