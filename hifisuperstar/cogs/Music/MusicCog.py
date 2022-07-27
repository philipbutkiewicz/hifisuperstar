# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2022 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import re
import validators
from hifisuperstar.core.Music.Player import Player
from hifisuperstar.core.Music.Playlist import Playlist
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import warn
from hifisuperstar.io.Logger import error
from hifisuperstar.core.Acl.Acl import Acl
from hifisuperstar.core.Acl import Rule
from hifisuperstar.core.Server.Server import check_server
from hifisuperstar.core.Server.Server import join_voice
from discord.ext import commands


# noinspection DuplicatedCode
class MusicCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.players = {}

    async def get_player(self, ctx):
        if not await check_server(ctx):
            return None

        if str(ctx.guild.id) not in self.players:
            self.players[str(ctx.guild.id)] = Player(ctx, self.config)

        return self.players[str(ctx.guild.id)]

    @commands.slash_command(description='Plays or queues media, YouTube links, YouTube search queries and direct media '
                                        'links are supported.')
    async def play(self, ctx, query=None):
        info(self, 'Playback request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_PLAY, ctx):
            return False

        info(self, f"Playback request{': ' + query if not query is None else ''}", ctx.guild)

        if not await join_voice(ctx):
            return False

        player = await self.get_player(ctx)
        if not player:
            error(self, 'Failed to get the player', ctx.guild)
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        await ctx.respond('Hold on, let me look that up...')
        track_info = player.queue_track(query)
        if not track_info:
            error(self, 'Failed to queue', ctx.guild)
            return await ctx.respond(f"ERROR: Failed to queue '{'the current playlist' if query is None else query}'")

        await ctx.respond(f"Queued '{track_info['title'] if not query is None else 'the current playlist'}'!")

    @commands.slash_command(description='This command can queue a YouTube playlist if supplied with a valid URL, '
                                        'or load a saved playlist')
    async def playlist(self, ctx, query):
        info(self, 'Playback (playlist) request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_QUEUE, ctx):
            return False

        info(self, f"Playback (playlist) request: '{query}'", ctx.guild)

        player = await self.get_player(ctx)
        if not player:
            error(self, 'Failed to get the player', ctx.guild)
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        player.stop_track()

        if not validators.url(query):
            if not re.match('^[a-zA-Z0-9\\-]+$', query):
                warn(self, 'Invalid input', ctx.guild)
                return await ctx.respond('ERROR: Invalid format, only alphanumeric characters or URLs are allowed.')

        await ctx.respond('Go get yourself a coffee, this can take a while...')
        playlist_info = await player.queue_playlist(query)
        if not playlist_info:
            error(self, 'Failed to queue', ctx.guild)
            return await ctx.respond(f"ERROR: Failed to queue '{query}'")

        await ctx.respond(f"Queued {len(playlist_info)} items!")

    @commands.slash_command(description='Lists available playlists')
    async def list_playlists(self, ctx):
        info(self, 'List playlists request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_LIST, ctx):
            return False

        player = await self.get_player(ctx)
        if not player:
            error(self, 'Failed to get the player', ctx.guild)
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        playlists = player.get_playlist().get_available_playlists()
        if not playlists:
            error(self, 'Failed to list playlists', ctx.guild)
            return await ctx.respond(f"ERROR: Failed to list playlists")

        message = 'Available playlists:```'
        for playlist in playlists:
            message += f"- {playlist}\n"
        message += '```'

        await ctx.respond(
            f"You can also view available playlists here: "
            f"{self.config['Web']['Base_Url']}/playlists/{str(ctx.guild.id)}")
        await ctx.respond(message)

    @commands.slash_command(description='Previews the current playlist')
    async def playlist_preview(self, ctx, name):
        info(self, 'preview playlist request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_LIST, ctx):
            return False

        if not validators.url(name):
            if not re.match('^[a-zA-Z0-9\\-]+$', name):
                warn(self, 'Invalid input', ctx.guild)
                return await ctx.respond('ERROR: Invalid format, only alphanumeric characters or URLs are allowed.')

        playlist = Playlist(ctx.guild.id, name)
        if not playlist.load_from_storage():
            return await ctx.respond('Could not find a playlist with that name.')

        await ctx.respond(
            f"You can view the contents of this playlist here: "
            f"{self.config['Web']['Base_Url']}/playlists/{str(ctx.guild.id)}/{name}")

    # noinspection DuplicatedCode
    @commands.slash_command(description='Saves the current playlist')
    async def playlist_save(self, ctx, name):
        info(self, 'Save playlist request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_SAVE, ctx):
            return False

        player = await self.get_player(ctx)
        if not player:
            error(self, 'Failed to get the player', ctx.guild)
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        if not validators.url(name):
            if not re.match('^[a-zA-Z0-9\\-]+$', name):
                warn(self, 'Invalid input', ctx.guild)
                return await ctx.respond('ERROR: Invalid format, only alphanumeric characters or URLs are allowed.')

        await ctx.respond('Saving the playlist...')
        playlist = player.get_playlist()
        playlist.set_name(name)

        if not playlist.save():
            error(self, 'Failed to save the playlist', ctx.guild)
            return await ctx.respond(f"ERROR: Failed to save playlist '{name}'")

        await ctx.respond('Playlist saved!')

    @commands.slash_command(description='Deletes a playlist with a given name')
    @commands.has_role('Admin')
    async def playlist_delete(self, ctx, name):
        info(self, 'Delete playlist request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_DELETE, ctx):
            return False

        if not validators.url(name):
            if not re.match('^[a-zA-Z0-9\\-]+$', name):
                warn(self, 'Invalid input', ctx.guild)
                return await ctx.respond('ERROR: Invalid format, only alphanumeric characters or URLs are allowed.')

        playlist = Playlist(ctx.guild.id, name)
        if not playlist.load_from_storage():
            warn(self, 'Playlist not found', ctx.guild)
            return await ctx.respond(f"ERROR: Playlist '{name}' not found!")

        if not playlist.delete():
            error(self, 'Failed to delete the playlist', ctx.guild)
            return await ctx.respond(f"ERROR: Failed to delete playlist '{name}'")

        await ctx.respond('Playlist deleted!')

    @commands.slash_command(description='Stops playback')
    async def stop(self, ctx):
        info(self, 'Playback stop request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_STOP, ctx):
            return False

        info(self, 'Stopping playback', ctx.guild)

        player = await self.get_player(ctx)
        if not player:
            error(self, 'Failed to get the player', ctx.guild)
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        await player.stop_track()
        player.get_playlist().clear()

        await ctx.respond('Done!')

    @commands.slash_command(description='Skips current item in the playback queue')
    async def skip(self, ctx):
        info(self, 'Go to next request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_SKIP, ctx):
            return False

        info(self, 'Skipping a track', ctx.guild)

        player = await self.get_player(ctx)
        if not player:
            error(self, 'Failed to get the player', ctx.guild)
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        player.skip_track()

        await ctx.respond('Done!')

    @commands.slash_command(description='Skips to a specific index in the queue')
    async def jump_to_index(self, ctx, index):
        info(self, 'Go to index request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_SKIP, ctx):
            return False

        info(self, f"Jumping to playlist index {index}", ctx.guild)

        player = await self.get_player(ctx)
        if not player:
            error(self, 'Failed to get the player', ctx.guild)
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        playlist = player.get_playlist()

        index = int(index)
        if index < 1 or index > len(playlist.get_tracks()):
            warn(self, 'Invalid input', ctx.guild)
            await ctx.respond(f"ERROR: Invalid format, provide a value between 1 and {len(playlist.get_tracks())}")
            return False

        player.skip_track_to_index(index - 1)

        await ctx.respond('Done!')

    @commands.slash_command(description='Goes back to the previous item in the playback queue')
    async def prev(self, ctx):
        info(self, 'Go to previous request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_SKIP, ctx):
            return False

        info(self, 'Going to a previous a track', ctx.guild)

        player = await self.get_player(ctx)
        if not player:
            error(self, 'Failed to get the player', ctx.guild)
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        player.prev_track()

        await ctx.respond('Done!')

    @commands.slash_command(description='Lists all items in the playback queue')
    async def queue(self, ctx):
        info(self, 'List queue items request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_QUEUE, ctx):
            return False

        info(self, 'Displaying the queue', ctx.guild)

        player = await self.get_player(ctx)
        if not player:
            error(self, 'Failed to get the player', ctx.guild)
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        display_queue_items = int(self.config['MusicCog']['Display_Queue_Items'])
        if display_queue_items < 10:
            warn(self, 'Queue misconfigured', ctx.guild)
            return await ctx.respond('ERROR: Queue misconfigured')

        playlist = player.get_playlist()
        queue = playlist.get_tracks()
        current_track = playlist.get_current_track()

        if len(queue) == 0:
            return await ctx.respond('ERROR: There is nothing in the queue')

        min_items = playlist.get_current_track_index() - (display_queue_items / 2) \
            if len(queue) > display_queue_items else playlist.get_current_track_index()
        max_items = playlist.get_current_track_index() + (display_queue_items / 2) \
            if playlist.get_current_track_index() + (display_queue_items / 2) < len(queue) else len(queue)

        message = '```'
        for i in range(int(min_items), int(max_items)):
            is_current = current_track['id'] == queue[i]['id'] if current_track else False
            message += f"{'==> ' if is_current else ''}{queue.index(queue[i]) + 1}. {queue[i]['title']}\n"
        message += '```'

        await ctx.respond(message)

    @commands.slash_command(description='Shows the most played tracks (in descending order)')
    async def top_tracks(self, ctx):
        info(self, 'List top tracks request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_TOP_TRACKS, ctx):
            return False

        info(self, 'Displaying top tracks', ctx.guild)

        player = await self.get_player(ctx)
        if not player:
            error(self, 'Failed to get the player', ctx.guild)
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        display_num_top_tracks = int(self.config['MusicCog']['Display_Num_Top_Tracks'])
        if display_num_top_tracks == 0:
            warn(self, 'Top tracks misconfigured', ctx.guild)
            return await ctx.respond('ERROR: Top tracks misconfigured')

        tracks = player.get_play_counter().get_all_counts()
        if len(tracks) == 0:
            return await ctx.respond('ERROR: Not enough top tracks to display')

        await ctx.respond(f"Displaying {display_num_top_tracks} top tracks:")

        tracks_keys = list(tracks.keys())

        if display_num_top_tracks > len(tracks):
            display_num_top_tracks = len(tracks)

        message = '```'
        for i in range(0, display_num_top_tracks):
            track = tracks[tracks_keys[i]]
            message += f"{i + 1}. {track['title']} ({track['count']} plays)\n"
        message += '```'

        await ctx.respond(message)

    @commands.slash_command(description='Sets playback volume to a provided value between 0 and 1.0')
    async def volume(self, ctx, volume):
        info(self, 'Volume change request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_SET_VOLUME, ctx):
            return False

        info(self, 'Setting volume', ctx.guild)

        player = await self.get_player(ctx)
        if not player:
            error(self, 'Failed to get the player', ctx.guild)
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        try:
            volume = float(volume)
        except ValueError:
            warn(self, 'Invalid input', ctx.guild)
            return await ctx.respond('ERROR: Invalid format, not a float number')

        if volume < 0 or volume > 1:
            warn(self, 'Invalid input', ctx.guild)
            return await ctx.respond('ERROR: Invalid format, provide a value between 0 and 1.0')

        if player.set_volume(volume):
            warn(self, 'Invalid input', ctx.guild)
            return await ctx.respond(f"Volume is now set at {volume * 100}%")

        await ctx.respond('ERROR: Failed setting volume')

    @commands.slash_command(brief='Toggles repeat mode or on off')
    async def repeat(self, ctx):
        info(self, 'Repeat mode change request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_SET_REPEAT, ctx):
            return False

        info(self, 'Toggling repeat mode', ctx.guild)

        player = await self.get_player(ctx)
        if not player:
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        repeat = player.set_repeat()

        await ctx.respond(f"Repeat is now {'on' if repeat else 'off'}")

    @commands.slash_command(description='Toggles repeat all mode or on off')
    async def repeat_all(self, ctx):
        info(self, 'Repeat all mode change request')

        if not await check_server(ctx):
            error(self, 'Server verification failed')
            return False

        if not await Acl(ctx.guild.id).check_and_fail(Rule.MUSIC_SET_REPEAT, ctx):
            return False

        info(self, 'Toggling repeat all mode', ctx.guild)

        player = await self.get_player(ctx)
        if not player:
            return await ctx.respond('ERROR: Failed to get the player for this Discord server')

        repeat = player.set_repeat_all()

        await ctx.respond(f"Repeat is now {'on' if repeat else 'off'}")
