#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import json
import os
import random
import tempfile

from hifisuperstar.io.Logger import error
from hifisuperstar.io.Resources import read_json_safe, write_json_atomic
from hifisuperstar.io.Strings import str_hash_sha256, str_rand_crc32


class Playlist:
    def __init__(self, guild_id, name="Default"):
        self.guild_id = str(guild_id)
        self.name = name
        self.tracks = []

        self.current_index = 0

        # Shuffle bookkeeping (track IDs): what already played in this round and the order it played in
        self.shuffle_played = set()
        self.shuffle_history = []

    def get_playlist_storage_path(self):
        guild_playlist_storage_path = os.path.join(
            "storage", "playlists", self.guild_id
        )
        os.makedirs(guild_playlist_storage_path, exist_ok=True)

        return guild_playlist_storage_path

    def get_playlist_path(self):
        return os.path.join(
            self.get_playlist_storage_path(), f"{str_hash_sha256(self.name)}.json"
        )

    def get_available_playlists(self):
        list_path = os.path.join(self.get_playlist_storage_path(), "list.json")
        available_playlists = read_json_safe(list_path, [])

        return available_playlists if isinstance(available_playlists, list) else []

    def load_from_storage(self):
        playlist_path = self.get_playlist_path()

        if not os.path.exists(playlist_path):
            return False

        playlist = read_json_safe(playlist_path)
        if not playlist or not isinstance(playlist, dict):
            return False

        if (
            "name" not in playlist
            or "guild_id" not in playlist
            or "tracks" not in playlist
        ):
            return False

        self.name = playlist["name"]
        self.guild_id = playlist["guild_id"]
        self.tracks = playlist["tracks"]

        return True

    def save(self, cache=False, overwrite=False):
        playlist_path = self.get_playlist_path()
        if os.path.exists(playlist_path) and not overwrite:
            error(
                self,
                f"Failed saving the playlist to {playlist_path} because path already exists!",
            )
            return False

        try:
            write_json_atomic(
                playlist_path,
                {
                    "name": self.name,
                    "guild_id": self.guild_id,
                    "tracks": self.tracks,
                },
            )
        except (OSError, TypeError, ValueError):
            error(self, f"Failed saving the playlist to {playlist_path}")
            return False

        if not cache:
            available_playlists = self.get_available_playlists()
            if self.name not in available_playlists:
                available_playlists.append(self.name)

            if not self.save_available_playlists(available_playlists):
                return False

        return True

    def save_available_playlists(self, available_playlists):
        list_path = os.path.join(self.get_playlist_storage_path(), "list.json")
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=os.path.dirname(list_path), delete=False
            ) as outfile:
                temporary_path = outfile.name
                json.dump(available_playlists, outfile)
            os.replace(temporary_path, list_path)
        except (OSError, TypeError, ValueError) as exc:
            error(self, f"Failed saving available playlists to {list_path}: {exc}")
            return False
        finally:
            if temporary_path is not None and os.path.exists(temporary_path):
                os.unlink(temporary_path)

        return True

    def rename(self, new_name):
        old_name = self.name
        new_path = Playlist(self.guild_id, new_name).get_playlist_path()
        destination_created = False
        index_updated = False
        renamed = False
        try:
            old_path = self.get_playlist_path()
            if not self.load_from_storage():
                error(self, f"Failed renaming playlist '{old_name}': not found")
                return False
            if old_name == new_name:
                return True
            available_playlists = self.get_available_playlists()
            if new_name in available_playlists or os.path.exists(new_path):
                error(self, f"Failed renaming playlist: '{new_name}' already exists")
                return False
            renamed_playlists = [
                new_name if name == old_name else name for name in available_playlists
            ]
            if new_name not in renamed_playlists:
                renamed_playlists.append(new_name)
            with open(new_path, "x", encoding="utf-8") as outfile:
                destination_created = True
                json.dump(
                    {"name": new_name, "guild_id": self.guild_id, "tracks": self.tracks},
                    outfile,
                )
            if not self.save_available_playlists(renamed_playlists):
                return False
            index_updated = True
            os.remove(old_path)
            self.name = new_name
            renamed = True
            return True
        except (OSError, TypeError, ValueError) as exc:
            error(self, f"Failed renaming playlist '{old_name}' to '{new_name}': {exc}")
            return False
        finally:
            if destination_created and not renamed:
                if index_updated and not self.save_available_playlists(
                    available_playlists
                ):
                    error(
                        self, f"Failed restoring playlist index after renaming '{old_name}'"
                    )
                try:
                    os.remove(new_path)
                except OSError as exc:
                    error(
                        self,
                        f"Failed removing incomplete renamed playlist '{new_path}': {exc}",
                    )

    def delete(self):
        if not self.load_from_storage():
            error(
                self,
                f"Failed deleting playlist {self.name} because it could not be loaded from storage",
            )
            return False

        # Cached playlists (e.g. imported YouTube ones) are not part of the index
        available_playlists = self.get_available_playlists()
        if self.name in available_playlists:
            available_playlists.remove(self.name)
            if not self.save_available_playlists(available_playlists):
                error(self, f"Failed removing {self.name} from the playlist index")
                return False

        try:
            os.remove(self.get_playlist_path())
        except OSError as exc:
            error(self, f"Failed deleting playlist {self.name}: {exc}")
            return False

        return True

    def get_name(self):
        return self.name

    def set_name(self, name):
        self.name = name

    def add_track(self, title, url):
        # Shuffle and removal identify tracks by ID, so an ID must never be used twice
        existing_ids = {track["id"] for track in self.tracks}
        tid = str_rand_crc32()
        while tid in existing_ids:
            tid = str_rand_crc32()
        self.tracks.append({"id": tid, "title": title, "url": url})

        # If playback had naturally run off the end of the list (current_index == -1), queuing a
        # new track needs to become the new "current" one, otherwise nothing will play until /stop.
        if self.current_index == -1:
            self.current_index = len(self.tracks) - 1

        return True

    def remove_track(self, tid):
        for index, track in enumerate(self.tracks):
            if track["id"] == tid:
                # Goes through remove_track_at_index so the current position stays on the same track
                return self.remove_track_at_index(index) is not None

        return False

    def remove_track_at_index(self, index):
        if index < 0 or index >= len(self.tracks):
            return None

        track = self.tracks.pop(index)

        # Keep current_index pointing at the same actual track after the list shifts
        if index < self.current_index:
            self.current_index -= 1
        elif index == self.current_index and self.current_index >= len(self.tracks):
            self.current_index = len(self.tracks) - 1 if self.tracks else -1

        return track

    def is_over(self):
        return self.current_index == (len(self.tracks) - 1)

    def get_tracks(self):
        return self.tracks

    def get_current_track(self):
        if (
            len(self.tracks) == 0
            or self.current_index < 0
            or self.current_index >= len(self.tracks)
        ):
            return None

        return self.tracks[self.current_index]

    def get_current_track_index(self):
        return self.current_index

    def clear(self):
        self.current_index = 0
        self.tracks.clear()
        self.reset_shuffle()

    def reset_shuffle(self):
        self.shuffle_played.clear()
        self.shuffle_history.clear()

    def shuffle_next(self):
        """Moves to a random track that has not played yet; returns None (index -1) once all have."""
        if len(self.tracks) == 0:
            return None

        current = self.get_current_track()
        if current is not None:
            self.shuffle_played.add(current["id"])
            self.shuffle_history.append(current["id"])
            del self.shuffle_history[:-200]

        candidates = [
            index
            for index, track in enumerate(self.tracks)
            if track["id"] not in self.shuffle_played and index != self.current_index
        ]
        if not candidates:
            self.current_index = -1
            return None

        self.current_index = random.choice(candidates)

        return self.get_current_track()

    def shuffle_prev(self):
        """Goes back to the track that actually played before the current one."""
        while self.shuffle_history:
            track_id = self.shuffle_history.pop()
            for index, track in enumerate(self.tracks):
                if track["id"] == track_id:
                    # The track we are leaving becomes unplayed again so it can come back later
                    current = self.get_current_track()
                    if current is not None:
                        self.shuffle_played.discard(current["id"])
                    self.current_index = index
                    return track

        return self.prev_track()

    def remember_current(self):
        """Records the current track as played (used when jumping around in shuffle mode)."""
        current = self.get_current_track()
        if current is not None:
            self.shuffle_played.add(current["id"])
            self.shuffle_history.append(current["id"])
            del self.shuffle_history[:-200]

    def skip_track(self):
        if len(self.tracks) == 0:
            return None

        if self.current_index < (len(self.tracks) - 1):
            self.current_index += 1
        else:
            self.current_index = -1

        return self.get_current_track()

    def prev_track(self):
        if len(self.tracks) == 0:
            return None

        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.tracks) - 1

        return self.get_current_track()

    def jump_to(self, index):
        if len(self.tracks) == 0 or index < 0 or index > (len(self.tracks) - 1):
            return None

        self.current_index = index

        return self.get_current_track()
