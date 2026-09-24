# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import io
import os
import re
import time
import asyncio
import threading
import discord
import boto3
import validators
from zipfile import ZipFile
from urllib.parse import urlparse
from yt_dlp import YoutubeDL
from discord import app_commands
from hifisuperstar.core.Music.Player import Player
from hifisuperstar.core.Music.Playlist import Playlist
from hifisuperstar.core.Music.MediaSourceProcessing.YouTube import get_ydl_opts
from hifisuperstar.core.Music.MediaSourceProcessing.YouTube import media_search_youtube
from hifisuperstar.io.Logger import info
from hifisuperstar.io.Logger import warn
from hifisuperstar.io.Logger import error
from hifisuperstar.io.Strings import allowed_chars_regex
from hifisuperstar.io.Strings import str_hash_sha256
from hifisuperstar.core.Acl.Acl import Acl
from hifisuperstar.core.Acl import Rule
from hifisuperstar.core.Server.Server import check_server
from hifisuperstar.core.Server.Server import join_voice
from hifisuperstar.core.Server.Server import respond
from discord.ext import commands


PLAYLIST_TRACKS_PER_PAGE = 20
PLAYLIST_DOWNLOADS_PER_PAGE = 20
SEARCH_RESULTS_LIMIT = 25
SEARCH_RESULTS_PER_PAGE = 10

# Characters that are invalid in Windows/Unix filenames or inside zip entries
_invalid_filename_chars_regex = re.compile(r'[\\/:*?"<>|]')

# Strips the "-<timestamp>.zip" suffix appended to generated package keys, leaving the playlist name
_package_name_regex = re.compile(r'-\d+\.zip$')


def sanitize_filename(name: str) -> str:
    return _invalid_filename_chars_regex.sub('_', name).strip()


def resolve_track_cache_url(track_url: str) -> str:
    # Tracks queued via a search query store the raw query as 'url', but the cache is keyed by the
    # resolved YouTube watch URL, so it needs to be looked up again (metadata only, no download).
    if validators.url(track_url):
        return track_url

    with YoutubeDL({'format': 'm4a/bestaudio/best', 'noplaylist': True, 'quiet': True}) as ydl:
        yt_info = ydl.extract_info(f"ytsearch:{track_url}", download=False)['entries'][0]
        return f"https://youtube.com/watch?v={yt_info['id']}"


def is_youtube_url(url: str) -> bool:
    domain = urlparse(url.lower().replace('www.', '')).netloc
    return domain in ('youtube.com', 'youtu.be')


def format_duration(seconds) -> str:
    seconds = int(seconds)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def download_and_cache_youtube_track(url: str):
    with YoutubeDL(get_ydl_opts(url)) as ydl:
        ydl.download([url])


def get_s3_client(s3_config: dict):
    return boto3.client(
        's3',
        endpoint_url=s3_config['Endpoint_Url'],
        region_name=s3_config.get('Region'),
        aws_access_key_id=s3_config['Access_Key_Id'],
        aws_secret_access_key=s3_config['Secret_Access_Key']
    )


def build_download_url(s3_config: dict, client, key: str) -> str:
    public_url_base = s3_config.get('Public_Url_Base')
    if public_url_base:
        return f"{public_url_base.rstrip('/')}/{key}"

    return client.generate_presigned_url(
        'get_object',
        Params={'Bucket': s3_config['Bucket'], 'Key': key},
        ExpiresIn=int(s3_config.get('Presigned_Url_Expiry_Seconds', 3600))
    )


def upload_zip_to_s3(s3_config: dict, key: str, data: bytes, progress_callback=None) -> str:
    client = get_s3_client(s3_config)
    client.upload_fileobj(
        io.BytesIO(data),
        s3_config['Bucket'],
        key,
        ExtraArgs={'ContentType': 'application/zip'},
        Callback=progress_callback
    )
    return build_download_url(s3_config, client, key)


def list_playlist_packages(s3_config: dict, guild_id: str) -> list:
    client = get_s3_client(s3_config)
    response = client.list_objects_v2(Bucket=s3_config['Bucket'], Prefix=f"playlists/{guild_id}/")

    packages = []
    for obj in response.get('Contents', []):
        key = obj['Key']
        filename = key.rsplit('/', 1)[-1]
        packages.append({
            'key': key,
            'name': _package_name_regex.sub('', filename),
            'last_modified': obj['LastModified']
        })

    packages.sort(key=lambda pkg: pkg['last_modified'], reverse=True)
    return packages


def get_playlist_package_download_url(s3_config: dict, key: str) -> str:
    client = get_s3_client(s3_config)
    return build_download_url(s3_config, client, key)


class PlaylistPageView(discord.ui.View):
    def __init__(self, playlist: Playlist, per_page: int = PLAYLIST_TRACKS_PER_PAGE, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.playlist = playlist
        self.per_page = per_page
        self.page = 0
        self.max_page = max(0, (len(playlist.get_tracks()) - 1) // per_page)
        self.message = None
        self._update_button_state()

    def _update_button_state(self):
        self.first_page.disabled = self.page == 0
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.max_page
        self.last_page.disabled = self.page >= self.max_page

    def build_embed(self) -> discord.Embed:
        tracks = self.playlist.get_tracks()
        start = self.page * self.per_page
        end = min(start + self.per_page, len(tracks))

        lines = []
        for i in range(start, end):
            title = tracks[i]['title']
            url = tracks[i].get('url')
            track_label = f"[{title}]({url})" if url else title
            lines.append(f"`{i + 1}.` {track_label}")

        embed = discord.Embed(
            title=f"Playlist: {self.playlist.get_name()}",
            description='\n'.join(lines) if lines else 'This playlist is empty.',
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1} — {len(tracks)} track(s) total")

        return embed

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label='⏮ First', style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='◀ Prev', style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='Next ▶', style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.max_page, self.page + 1)
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='Last ⏭', style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.max_page
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class PlaylistDownloadsView(discord.ui.View):
    def __init__(self, s3_config: dict, packages: list, per_page: int = PLAYLIST_DOWNLOADS_PER_PAGE, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.s3_config = s3_config
        self.packages = packages
        self.per_page = per_page
        self.page = 0
        self.max_page = max(0, (len(packages) - 1) // per_page)
        self.message = None
        self._build_select()
        self._update_button_state()

    def _current_page_items(self) -> list:
        start = self.page * self.per_page
        end = min(start + self.per_page, len(self.packages))
        return self.packages[start:end]

    def _build_select(self):
        for item in [child for child in self.children if isinstance(child, discord.ui.Select)]:
            self.remove_item(item)

        select = discord.ui.Select(placeholder='Choose a package to download...', row=0)
        for pkg in self._current_page_items():
            select.add_option(
                label=pkg['name'][:100],
                description=pkg['last_modified'].strftime('%Y-%m-%d %H:%M UTC'),
                value=pkg['key']
            )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        key = interaction.data['values'][0]

        try:
            url = await asyncio.to_thread(get_playlist_package_download_url, self.s3_config, key)
        except Exception as e:
            return await interaction.response.send_message(f"ERROR: Failed to generate a download link ({e})", ephemeral=True)

        link_view = discord.ui.View()
        link_view.add_item(discord.ui.Button(label='Download', style=discord.ButtonStyle.link, url=url, emoji='⬇️'))
        await interaction.response.send_message(view=link_view, ephemeral=True)

    def _update_button_state(self):
        self.first_page.disabled = self.page == 0
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.max_page
        self.last_page.disabled = self.page >= self.max_page

    def build_embed(self) -> discord.Embed:
        start = self.page * self.per_page
        lines = [
            f"`{i}.` **{pkg['name']}** — {pkg['last_modified'].strftime('%Y-%m-%d %H:%M UTC')}"
            for i, pkg in enumerate(self._current_page_items(), start=start + 1)
        ]

        embed = discord.Embed(
            title='Generated Playlist Packages',
            description='\n'.join(lines) if lines else 'No packages have been generated yet.',
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1} — {len(self.packages)} package(s) total")

        return embed

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label='⏮ First', style=discord.ButtonStyle.secondary, row=1)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='◀ Prev', style=discord.ButtonStyle.primary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='Next ▶', style=discord.ButtonStyle.primary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.max_page, self.page + 1)
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='Last ⏭', style=discord.ButtonStyle.secondary, row=1)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.max_page
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class QueuePageView(discord.ui.View):
    def __init__(self, player, per_page: int = PLAYLIST_TRACKS_PER_PAGE, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.player = player
        self.per_page = per_page
        playlist = player.get_playlist()
        self.max_page = max(0, (len(playlist.get_tracks()) - 1) // per_page)
        self.page = min(self.max_page, playlist.get_current_track_index() // per_page)
        self.message = None
        self._build_select()
        self._update_button_state()

    def _current_page_tracks(self):
        tracks = self.player.get_playlist().get_tracks()
        start = self.page * self.per_page
        end = min(start + self.per_page, len(tracks))
        return start, tracks[start:end]

    def _build_select(self):
        for item in [child for child in self.children if isinstance(child, discord.ui.Select)]:
            self.remove_item(item)

        start, tracks = self._current_page_tracks()
        if not tracks:
            return

        current_track = self.player.get_playlist().get_current_track()
        select = discord.ui.Select(placeholder='Jump to a track...', row=0)
        for i, track in enumerate(tracks, start=start):
            is_current = current_track is not None and current_track['id'] == track['id']
            select.add_option(
                label=f"{i + 1}. {track['title']}"[:100],
                value=str(i),
                default=is_current,
                emoji='▶️' if is_current else None
            )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        index = int(interaction.data['values'][0])
        self.player.skip_track_to_index(index)
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    def _update_button_state(self):
        self.first_page.disabled = self.page == 0
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.max_page
        self.last_page.disabled = self.page >= self.max_page

    def build_embed(self) -> discord.Embed:
        start, tracks = self._current_page_tracks()
        current_track = self.player.get_playlist().get_current_track()

        lines = []
        for i, track in enumerate(tracks, start=start):
            is_current = current_track is not None and current_track['id'] == track['id']
            title = track['title']
            url = track.get('url')
            track_label = f"[{title}]({url})" if url else title
            prefix = '▶ ' if is_current else f"`{i + 1}.`  "
            lines.append(f"{prefix}{track_label}")

        embed = discord.Embed(
            title='Queue',
            description='\n'.join(lines) if lines else 'There is nothing in the queue.',
            color=discord.Color.blurple()
        )
        total = len(self.player.get_playlist().get_tracks())
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1} — {total} track(s) total")

        return embed

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label='⏮ First', style=discord.ButtonStyle.secondary, row=1)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='◀ Prev', style=discord.ButtonStyle.primary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='Next ▶', style=discord.ButtonStyle.primary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.max_page, self.page + 1)
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='Last ⏭', style=discord.ButtonStyle.secondary, row=1)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.max_page
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class SearchResultsView(discord.ui.View):
    def __init__(self, cog: 'MusicCog', query: str, results: list, per_page: int = SEARCH_RESULTS_PER_PAGE, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.query = query
        self.results = results
        self.per_page = per_page
        self.page = 0
        self.max_page = max(0, (len(results) - 1) // per_page)
        self.message = None
        self._build_select()
        self._update_button_state()

    def _current_page_items(self):
        start = self.page * self.per_page
        end = min(start + self.per_page, len(self.results))
        return start, self.results[start:end]

    def _build_select(self):
        for item in [child for child in self.children if isinstance(child, discord.ui.Select)]:
            self.remove_item(item)

        start, items = self._current_page_items()
        if not items:
            return

        select = discord.ui.Select(placeholder='Choose a track to play...', row=0)
        for i, entry in enumerate(items, start=start):
            duration = entry.get('duration')
            uploader = entry.get('uploader') or entry.get('channel')
            description_parts = [part for part in (uploader, format_duration(duration) if duration else None) if part]
            select.add_option(
                label=f"{i + 1}. {entry.get('title', 'Unknown')}"[:100],
                description=' — '.join(description_parts)[:100] if description_parts else None,
                value=str(i)
            )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        index = int(interaction.data['values'][0])
        entry = self.results[index]
        video_url = f"https://youtube.com/watch?v={entry['id']}"

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(content=f"🔎 Selected '{entry.get('title', video_url)}'!", embed=None, view=self)
        await self.cog.play_from_search(interaction, video_url)

    def _update_button_state(self):
        self.first_page.disabled = self.page == 0
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.max_page
        self.last_page.disabled = self.page >= self.max_page

    def build_embed(self) -> discord.Embed:
        start, items = self._current_page_items()

        lines = []
        for i, entry in enumerate(items, start=start):
            title = entry.get('title', 'Unknown')
            video_url = f"https://youtube.com/watch?v={entry['id']}"
            duration = entry.get('duration')
            suffix = f" ({format_duration(duration)})" if duration else ''
            lines.append(f"`{i + 1}.` [{title}]({video_url}){suffix}")

        embed = discord.Embed(
            title=f"Search results for '{self.query}'",
            description='\n'.join(lines) if lines else 'No results found.',
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1} — {len(self.results)} result(s)")

        return embed

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label='⏮ First', style=discord.ButtonStyle.secondary, row=1)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='◀ Prev', style=discord.ButtonStyle.primary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='Next ▶', style=discord.ButtonStyle.primary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.max_page, self.page + 1)
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label='Last ⏭', style=discord.ButtonStyle.secondary, row=1)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.max_page
        self._build_select()
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


# noinspection DuplicatedCode
class MusicCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.players = {}
        self.playlist_downloads_in_progress = set()

    async def get_player(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return None

        if str(interaction.guild.id) not in self.players:
            self.players[str(interaction.guild.id)] = Player(interaction, self.config)

        return self.players[str(interaction.guild.id)]

    async def play_from_search(self, interaction: discord.Interaction, query: str):
        if not await join_voice(interaction):
            return False

        player = await self.get_player(interaction)
        if not player:
            error(self, 'Failed to get the player', interaction.guild)
            return await respond(interaction, 'ERROR: Failed to get the player for this Discord server')

        track_info = player.queue_track(query)
        if not track_info:
            error(self, 'Failed to queue', interaction.guild)
            return await respond(interaction, f"ERROR: Failed to queue '{query}'")

        await respond(interaction, f"Queued '{track_info['title']}'!")

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

    @app_commands.command(name='search', description='Searches YouTube and lets you pick a track from a list to play')
    async def search(self, interaction: discord.Interaction, query: str):
        info(self, 'Search request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_PLAY, interaction):
            return False

        info(self, f"Search request: '{query}'", interaction.guild)

        await respond(interaction, f"🔎 Searching YouTube for '{query}'...")

        try:
            results = await asyncio.to_thread(media_search_youtube, query, SEARCH_RESULTS_LIMIT)
        except Exception as e:
            error(self, f"Search failed ({e})", interaction.guild)
            return await respond(interaction, 'ERROR: Failed to search YouTube.')

        if not results:
            return await respond(interaction, f"No results found for '{query}'.")

        view = SearchResultsView(self, query, results)
        await respond(interaction, embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

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

    @app_commands.command(name='playlist_view', description='Displays the contents of a saved playlist')
    async def playlist_view(self, interaction: discord.Interaction, name: str):
        info(self, 'View playlist request')

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
            warn(self, 'Playlist not found', interaction.guild)
            return await respond(interaction, f"ERROR: Playlist '{name}' not found!")

        view = PlaylistPageView(playlist)
        if view.max_page > 0:
            await respond(interaction, embed=view.build_embed(), view=view)
            view.message = await interaction.original_response()
        else:
            await respond(interaction, embed=view.build_embed())

    async def _resolve_and_cache_track(self, track, interaction):
        track_url = track.get('url')
        if not track_url:
            return None

        try:
            cache_url = await asyncio.to_thread(resolve_track_cache_url, track_url)
        except Exception as e:
            warn(self, f"Track '{track['title']}' could not be resolved ({e}), skipping", interaction.guild)
            return None

        if not is_youtube_url(cache_url):
            warn(self, f"Track '{track['title']}' is not a YouTube source and can't be cached, skipping", interaction.guild)
            return None

        track_path = os.path.join('cache', f"{str_hash_sha256(cache_url)}.m4a")
        if not os.path.exists(track_path):
            info(self, f"Track '{track['title']}' not cached yet, fetching...", interaction.guild)
            try:
                await asyncio.to_thread(download_and_cache_youtube_track, cache_url)
            except Exception as e:
                warn(self, f"Track '{track['title']}' could not be fetched ({e}), skipping", interaction.guild)
                return None

        if not os.path.exists(track_path):
            warn(self, f"Track '{track['title']}' still missing from cache after fetching, skipping", interaction.guild)
            return None

        return track_path

    def _make_upload_progress_callback(self, interaction: discord.Interaction, label: str, total_bytes: int):
        # s3transfer invokes the callback from worker threads (possibly concurrently for multipart uploads)
        loop = asyncio.get_running_loop()
        lock = threading.Lock()
        state = {'uploaded': 0, 'last_step': -1}

        def on_progress(bytes_amount):
            with lock:
                state['uploaded'] += bytes_amount
                percent = int((state['uploaded'] / total_bytes) * 100) if total_bytes else 100
                step = min(100, (percent // 10) * 10)
                if step <= state['last_step']:
                    return
                state['last_step'] = step

            async def _update():
                try:
                    await interaction.edit_original_response(content=f"⬆️ Uploading '{label}': {step}%...")
                except discord.HTTPException:
                    pass

            asyncio.run_coroutine_threadsafe(_update(), loop)

        return on_progress

    @app_commands.command(name='playlist_download', description='Downloads a saved playlist as a zip file of cached tracks')
    async def playlist_download(self, interaction: discord.Interaction, name: str):
        info(self, 'Download playlist request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_DOWNLOAD, interaction):
            return False

        if not validators.url(name):
            if not re.match(allowed_chars_regex, name):
                warn(self, 'Invalid input', interaction.guild)
                return await respond(interaction, 'ERROR: Invalid format, only alphanumeric characters or URLs are allowed.')

        guild_id = str(interaction.guild.id)
        if guild_id in self.playlist_downloads_in_progress:
            warn(self, 'A playlist download is already in progress', interaction.guild)
            return await respond(interaction, 'ERROR: A playlist download is already in progress for this server, please wait for it to finish.')

        s3_config = self.config.get('MusicCog', {}).get('S3', {})
        if not s3_config.get('Enabled'):
            error(self, 'S3 upload is not configured', interaction.guild)
            return await respond(interaction, 'ERROR: Playlist downloads are not configured, ask an admin to set up S3 storage.')

        playlist = Playlist(interaction.guild.id, name)
        if not playlist.load_from_storage():
            warn(self, 'Playlist not found', interaction.guild)
            return await respond(interaction, f"ERROR: Playlist '{name}' not found!")

        tracks = playlist.get_tracks()
        if not tracks:
            warn(self, 'Playlist is empty', interaction.guild)
            return await respond(interaction, f"ERROR: Playlist '{name}' is empty!")

        self.playlist_downloads_in_progress.add(guild_id)
        try:
            await respond(interaction, f"⏳ Packing '{playlist.get_name()}': 0/{len(tracks)} tracks processed...")

            buffer = io.BytesIO()
            track_index = 0
            m3u_entries = []
            progress_step = max(1, len(tracks) // 10)
            with ZipFile(buffer, 'w') as zipfile:
                for position, track in enumerate(tracks, start=1):
                    track_path = await self._resolve_and_cache_track(track, interaction)
                    if track_path:
                        track_index += 1
                        entry_name = f"{str(track_index).rjust(3, '0')}. {sanitize_filename(track['title'])}.m4a"
                        zipfile.write(track_path, entry_name)
                        m3u_entries.append((track['title'], entry_name))

                    if position % progress_step == 0 or position == len(tracks):
                        try:
                            await interaction.edit_original_response(
                                content=f"⏳ Packing '{playlist.get_name()}': {position}/{len(tracks)} tracks processed ({track_index} cached)..."
                            )
                        except discord.HTTPException:
                            pass

                if m3u_entries:
                    m3u_lines = ['#EXTM3U']
                    for title, entry_name in m3u_entries:
                        m3u_lines.append(f"#EXTINF:-1,{title}")
                        m3u_lines.append(entry_name)
                    zipfile.writestr('playlist.m3u8', '\n'.join(m3u_lines) + '\n')

            if track_index == 0:
                error(self, 'No tracks available for download', interaction.guild)
                return await respond(interaction, f"ERROR: None of the tracks in '{name}' could be fetched or cached.")

            buffer.seek(0)
            zip_data = buffer.getvalue()

            object_key = f"playlists/{guild_id}/{sanitize_filename(playlist.get_name())}-{int(time.time())}.zip"
            progress_callback = self._make_upload_progress_callback(interaction, playlist.get_name(), len(zip_data))
            try:
                download_url = await asyncio.to_thread(upload_zip_to_s3, s3_config, object_key, zip_data, progress_callback)
            except Exception as e:
                error(self, f"Failed to upload playlist zip to S3 ({e})", interaction.guild)
                return await respond(interaction, 'ERROR: Failed to upload the playlist zip to storage.')

            await respond(interaction, f"✅ Here's '{playlist.get_name()}' ({track_index} track(s))!\n{download_url}")
        finally:
            self.playlist_downloads_in_progress.discard(guild_id)

    @app_commands.command(name='playlist_downloads', description='Lists previously generated playlist zip packages')
    async def playlist_downloads(self, interaction: discord.Interaction):
        info(self, 'List playlist downloads request')

        if not await check_server(interaction):
            error(self, 'Server verification failed')
            return False

        if not await Acl(interaction.guild.id).check_and_fail(Rule.MUSIC_PLAYLIST_DOWNLOAD, interaction):
            return False

        s3_config = self.config.get('MusicCog', {}).get('S3', {})
        if not s3_config.get('Enabled'):
            error(self, 'S3 upload is not configured', interaction.guild)
            return await respond(interaction, 'ERROR: Playlist downloads are not configured, ask an admin to set up S3 storage.')

        try:
            packages = await asyncio.to_thread(list_playlist_packages, s3_config, str(interaction.guild.id))
        except Exception as e:
            error(self, f"Failed to list playlist packages ({e})", interaction.guild)
            return await respond(interaction, 'ERROR: Failed to list playlist packages from storage.')

        if not packages:
            return await respond(interaction, 'No playlist packages have been generated yet.')

        view = PlaylistDownloadsView(s3_config, packages)
        await respond(interaction, embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

    # noinspection DuplicatedCode
    @app_commands.command(name='playlist_save', description='Saves the current playlist')
    async def playlist_save(self, interaction: discord.Interaction, name: str, overwrite: bool = False):
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

        if not playlist.save(overwrite=overwrite):
            error(self, 'Failed to save the playlist', interaction.guild)
            return await respond(interaction, f"ERROR: Failed to save playlist '{name}'"
                                  f"{', it already exists. Pass overwrite=True to replace it.' if not overwrite else ''}")


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

        if len(player.get_playlist().get_tracks()) == 0:
            return await respond(interaction, 'ERROR: There is nothing in the queue')

        display_queue_items = int(self.config['MusicCog']['Display_Queue_Items'])
        per_page = min(display_queue_items, 25) if display_queue_items >= 10 else PLAYLIST_TRACKS_PER_PAGE

        view = QueuePageView(player, per_page=per_page)
        await respond(interaction, embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

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
