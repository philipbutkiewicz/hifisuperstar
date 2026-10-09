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
- **User join messages** - sends a configurable message when someone joins the server.
- **ACL system** - per-server, per-user rule overrides for who can use what.
- **Optional web UI** - a small Flask app for browsing saved playlists.

Every cog above can be individually enabled/disabled in `config.json`.

## Requirements

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) available on your `PATH` (required for audio playback)
- Node.js 22+ or Deno 2.3+ available on the bot process's `PATH` (required for YouTube JavaScript challenges). Both are enabled; yt-dlp prefers Deno when available.
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

### YouTube track cache

Downloaded audio is stored in `cache/<hash>.m4a`; descriptive track metadata is
saved atomically in `cache/<hash>.info.json`. With both present, playback and
queueing use local files without contacting YouTube or requiring cookies or a
JavaScript runtime. Normalized audio under `normalized/cache/` is preferred when
available. Common watch, short-link, embed, and Shorts URLs share metadata/cache
lookups; repeated search queries also remember their resolved video.

Existing audio without metadata needs one successful YouTube lookup to populate
its sidecar, but is not downloaded again. Missing audio causes fresh extraction;
expiring stream URLs, formats, and authentication headers are not persisted or
reused. Unreadable or invalid metadata is logged and fetched again. Playlist
downloads also reuse cached audio and query resolutions. `/search` and playlist
imports still fetch their result lists from YouTube.

Failed YouTube fetches (including read timeouts and HTTP 403 errors) are retried
three times after the initial attempt, with a five-second wait between attempts.
This applies to playback lookups, searches, playlist pages, and audio downloads.
Each retry is logged; failures that persist after all retries use the normal
error handling. Downloads re-extract media information on each retry rather than
reusing a failed stream URL.

Metadata has no automatic expiry. To refresh a cached search query or a video's
title, remove its `.info.json` sidecar(s); deleting the audio forces a fresh
extraction and download on the next play.

`/music_precache_queue` processes a snapshot of the entire current queue, including
tracks before the current position, and caches both metadata and audio. It runs
sequentially without changing playback, the queue, or its current position. No
voice connection or S3 configuration is required. It skips direct non-YouTube
URLs, continues after individual failures, and reports cached/already-cached/
skipped/failed totals. Only one precache operation runs per server at a time.
The status message refreshes every five seconds, including during a long download,
and shows the current track and completed counts. Updates use the bot's channel
message access rather than an expiring interaction token.
Tracks added afterwards require another run. Access follows the normal music ACL
defaults and can be overridden with the `MUSIC_PRECACHE_QUEUE` rule.

### YouTube authentication

YouTube extraction also requires a supported JavaScript runtime and the EJS
challenge solver, independently of cookies. `uv sync` installs the solver through
`yt-dlp[default]`; the Docker image includes Node.js. For a local install, ensure
`node --version` reports 22+ (or `deno --version` reports 2.3+) in the same
environment that starts the bot. A service does not necessarily inherit an
interactive shell's nvm `PATH`.

If you see **"Signature solving failed"**, **"n challenge solving failed"**, or
**"Only images are available"**, run `uv sync`, check the runtime's availability,
and restart the bot. Do not change the requested audio format to work around a
missing solver. See yt-dlp's [EJS setup guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

If yt-dlp reports **"Sign in to confirm you're not a bot"**, YouTube is rejecting
the unauthenticated request. The bot can pass an exported cookie file to yt-dlp
for playback, searches, playlist imports, and playlist downloads:

1. Follow yt-dlp's [YouTube cookie export instructions](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies).
   The file must use Netscape/Mozilla cookie format, not JSON.
2. Save it as `cookies/youtube.txt` under the project directory and restrict access
   (for example, `chmod 600 cookies/youtube.txt`). Cookies are account credentials:
   never paste them into chat, commit them, or share them. The `cookies/` directory
   is excluded from Git and Docker build contexts.
3. Set the environment variable before starting the bot:
   ```sh
   export HIFI_YOUTUBE_COOKIE_FILE="$PWD/cookies/youtube.txt"
   ./start.sh
   ```

The setting is process-wide, not per guild. Without it, extraction continues
without cookies. A configured file must exist and be readable and writable by
the bot (yt-dlp can update the cookie file). Replace expired cookies and restart
the bot when necessary. Authentication is not guaranteed to resolve every YouTube
restriction; account use with yt-dlp can also carry a risk of account bans.

For Docker, create a `docker-compose.override.yml` alongside the existing Compose
file so the cookie path is available **inside** the bot container:

```yaml
services:
  bot:
    environment:
      HIFI_YOUTUBE_COOKIE_FILE: /app/cookies/youtube.txt
    volumes:
      - ./cookies:/app/cookies
```

Then recreate the bot with `docker compose up --build -d bot`. Do not bake cookies
into an image.

## Docker

Install Docker with the Compose plugin, then create `config.json` from `config.json.example` and set `Bot.Token` as described above. Start the bot from the project directory:

```sh
docker compose up --build -d
docker compose logs -f bot
```

The container includes ffmpeg and uses the locked Python dependencies. `config.json` is mounted read-only; `storage/` (guild settings and playlists), `cache/` (downloaded audio), and `normalized/` are mounted from the host so they survive container replacement. The bot does not need an inbound port.

To also serve the optional playlist browser, set `FLASK_SECRET_KEY` to a strong random value in your shell and start the `web` profile:

```sh
export FLASK_SECRET_KEY="$(openssl rand -hex 32)"
docker compose --profile web up --build -d
```

The browser listens on `127.0.0.1:5000` by default. Set `WEB_BIND` and `WEB_PORT` before starting Compose if you need a different interface or port, and configure `Web.Base_Url` to the URL your users can reach. The Flask server is intended for local or reverse-proxied use, not direct public exposure. Stop both services with `docker compose --profile web down` (omit `--profile web` when only running the bot). If the web image has no Git metadata, the footer displays `unknown` unless `GIT_COMMIT_SHA` is supplied.

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
- `LLMCog` - OpenAI-compatible API URL/key/model, token limit, default system prompt, and reasoning effort. Model, token limit, reasoning effort, mode, web search limit, enabled state, and channel restriction can be overridden per server via the `/llm_*` commands. These settings are saved in `storage/llm.<guild_id>.json` and restored after restart; conversation history is not saved.

Server-facing values in the sections above are defaults. Put overrides in `Guilds` using the Discord server ID as a string; nested sections such as `MusicCog.S3` inherit unspecified defaults:

```json
"Guilds": {
   "123456789012345678": {
      "ImageSearchCog": {"Safe_Search": "Strict"},
      "MusicCog": {"Radio_URL": "https://example.com/other-radio.ogg"},
      "LLMCog": {"OpenAI_API_Model": "other-model"}
   }
}
```

This also applies to Spotify and LLM API credentials if servers use different accounts. `Bot.Token` and `Bot.Enabled_Cogs` remain process-wide. `Web.Enabled` starts no server by itself; a per-guild `Web` override only changes the playlist link displayed by the bot. Slash-command changes to LLM settings take precedence over defaults and `Guilds` overrides until changed again.

## Commands

During playback, the music player gives discord.py 10 seconds to restore a lost
voice connection, then makes up to three fresh connection attempts. If the audio
player has stopped, recovery restarts the current track from the beginning (or
restarts the radio stream), without advancing or clearing the queue. `/stop`
cancels recovery and disconnects. If all attempts fail, the failure is logged and
the player stops but keeps its queue; `/play` can reconnect and resume it without
requiring `/stop` first.

Commands are grouped roughly by cog. Admin-only commands are noted.

**Music**
`/play`, `/search`, `/play_radio`, `/playlist`, `/list_playlists`, `/playlist_view`, `/playlist_save`, `/playlist_delete`, `/playlist_rename`, `/playlist_download`, `/playlist_downloads`, `/music_precache_queue`, `/stop`, `/skip`, `/prev`, `/jump_to_index`, `/queue`, `/top_tracks`, `/volume`, `/repeat`, `/repeat_all`

`/playlist_rename name:<current name> new_name:<new name>` renames a saved playlist
in the current server, preserving its tracks and position in the saved-playlist
list. Existing destinations are never overwritten. It does not change the active
queue or playback. Like `/playlist_delete`, it requires the `Admin` role; access
can additionally be restricted with the `MUSIC_PLAYLIST_RENAME` ACL rule.

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

**User join**
`/set_userjoin_channel`, `/disable_userjoin`

**ACL** (admin-only)
`/set_rule`, `/clear_rules`, `/admin_mode`

## Optional web UI

`web/` is a small Flask app that lets you browse saved playlists in a browser. `start.sh` launches it alongside the bot. Set `Web.Enabled` to `true` and `Web.Base_Url` accordingly if you want the `/list_playlists` command to link to it.

## Contributing

PRs are welcome, but given the maintenance status above, please don't expect prompt reviews.
