# HiFi Superstar

A Discord bot that plays music, tells bad jokes, does image searches, has an optional LLM chat mode, and a handful of other server utilities. Commands are implemented as Discord **slash commands** (`/command`), not legacy text-prefixed commands.

## ⚠️ Disclaimer

This is a personal hobby project. It is only maintained sporadically (occasional bugfixes and dependency bumps when something breaks), not actively developed, and comes with **no support or warranty of any kind**. Using it is entirely at your own risk - review the code before running it, especially if you plan on granting it Administrator permissions on your server. It's been developed originally as a Python learning project. I couldn't be arsed to rewrite it properly since. Make of that what you will.

## What does it do?

- **Music** - plays audio from YouTube links, YouTube search queries, or direct media URLs; queues, saves/loads named playlists, imports YouTube playlists, downloads a saved playlist as a zip (uploaded to an S3-compatible bucket), and can play a configured internet radio stream.
- **Spotify** - imports a Spotify playlist's tracks into the music queue.
- **LLM chat** - optional OpenAI-API-compatible chat bot (via LangChain) that can be toggled on per server, restricted to a channel, and given tool access to music playback and image search.
- **Image search** - searches images via DuckDuckGo.
- **Jokes** - dad jokes, Chuck Norris jokes, and bad jokes.
- **Random pictures** - random cat/pug pictures from a local image folder.
- **Regex auto-responses** - per-server regex-triggered chat responses.
- **Selectable roles** - reaction-based self-assignable roles.
- **Anti-loudmouth** - monitors voice channel audio levels and can act on people who are too loud.
- **Voice recorder** - records voice channel audio.
- **User join messages** - sends a configurable message when someone joins the server.
- **ACL system** - per-server, per-user rule overrides for who can use what.
- **Optional web UI** - a small Flask app for browsing saved playlists.

Every cog above can be individually enabled/disabled in `config.json`.

## Requirements

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) available on your `PATH` (required for audio playback)
- A Discord bot application/token
- Dependencies are managed with [uv](https://github.com/astral-sh/uv) via `pyproject.toml` / `uv.lock`. A `requirements.txt` is also present but not the source of truth - prefer `uv sync`.

## Setup

1. Install dependencies:
   ```
   uv sync
   ```
   (or `pip install -r requirements.txt` if you're not using uv)
2. Create a Discord application at the [Discord Developer Portal](https://discord.com/developers/applications).
   - Under **Bot**, enable the **Presence Intent**, **Server Members Intent**, and **Message Content Intent**.
   - Under **OAuth2 → URL Generator**, select the `bot` and `applications.commands` scopes and whatever permissions you're comfortable granting (the bot uses voice channels, sends messages/embeds, manages roles if you use selectable roles, etc.).
   - Invite the bot to your server using the generated URL.
3. Copy `config.json.example` to `config.json` and fill in at least `Bot.Token`. Trim `Bot.Enabled_Cogs` to whichever cogs you actually want running, and fill in the config section for each enabled cog (Spotify credentials, LLM API details, S3 credentials for playlist zip downloads, etc.) - see the reference below.
4. Run it:
   ```
   ./start.sh
   ```
   or directly:
   ```
   uv run app.py
   ```

Slash commands are synced automatically on startup, so they should show up in Discord shortly after the bot connects.

### `config.json` reference

- `Bot.Token` - your Discord bot token.
- `Bot.Enabled_Cogs` - list of cog names to load (see the feature list above).
- `Web.Enabled` / `Web.Base_Url` - enables linking to the optional Flask playlist browser from `/list_playlists`.
- `MusicCog` - allowed MIME types for direct-link playback, how many tracks to show in `/top_tracks` and `/queue`, the radio stream URL, and an `S3` sub-section (Hetzner or any S3-compatible endpoint) used by `/playlist_download` / `/playlist_downloads`.
- `SpotifyCog` - Spotify API client ID/secret for `/spotify_import_playlist`.
- `AntiLoudmouthCog` - RMS decibel threshold for the loudmouth monitor.
- `JokesCog` - which joke types are enabled.
- `RandomPicturesCog` - which picture categories and file types are enabled.
- `RegexCog` - whether matched messages get logged.
- `ImageSearchCog` - max results and safe-search level.
- `LLMCog` - OpenAI-compatible API URL/key/model, token limit, default system prompt, and reasoning effort. Model, token limit, reasoning effort, enabled state, and channel restriction can also be overridden per-server at runtime via the `/llm_*` commands.

## Commands

Commands are grouped roughly by cog. Admin-only commands are noted.

**Music**
`/play`, `/search`, `/play_radio`, `/playlist`, `/list_playlists`, `/playlist_view`, `/playlist_save`, `/playlist_delete`, `/playlist_download`, `/playlist_downloads`, `/stop`, `/skip`, `/prev`, `/jump_to_index`, `/queue`, `/top_tracks`, `/volume`, `/repeat`, `/repeat_all`

**Spotify**
`/spotify_import_playlist`

**LLM** (admin-only except `/llm_context_clear`)
`/toggle_llm`, `/llm_set_channel`, `/llm_clear_channel`, `/llm_set_model_id`, `/llm_set_max_tokens`, `/llm_set_reasoning_effort`, `/llm_toggle_mode`, `/llm_context_clear`, `/llm_list_models`

**Image search**
`/image_search`, `/random_image_search`, `/image_search_config`

**Jokes**
`/dad`, `/chuck`, `/badjoke`

**Random pictures**
`/cat`, `/pug`

**Regex responses** (admin-only to manage)
`/set_regex_response`, `/delete_regex_response`, `/list_regex_responses`

**Selectable roles** (admin-only)
`/add_selectable_role`, `/remove_selectable_role`, `/selectable_roles`

**Voice / moderation** (admin-only)
`/start_recording`, `/stop_recording`, `/start_monitoring`, `/stop_monitoring`

**User join**
`/set_userjoin_channel`, `/disable_userjoin`

**ACL** (admin-only)
`/set_rule`, `/clear_rules`, `/admin_mode`

## Optional web UI

`web/` is a small Flask app that lets you browse saved playlists in a browser. `start.sh` launches it alongside the bot. Set `Web.Enabled` to `true` and `Web.Base_Url` accordingly if you want the `/list_playlists` command to link to it.

## Contributing

PRs are welcome, but given the maintenance status above, please don't expect prompt reviews.
