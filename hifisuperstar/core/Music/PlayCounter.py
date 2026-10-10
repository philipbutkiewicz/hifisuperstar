#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

from hifisuperstar.io.Resources import load_resource, save_resource


class PlayCounter:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.counts = load_resource("counts", self.guild_id)

    def save_counts(self):
        save_resource("counts", self.guild_id, self.counts)

    def clear(self):
        self.counts = {}

    def count_playback(self, track):
        # Track IDs are random per queue entry, the URL identifies the actual song
        key = track.get("url") or track["id"]
        if key not in self.counts:
            self.counts[key] = {
                "url": track["url"],
                "title": track["title"],
                "count": 0,
            }

        self.counts[key]["count"] += 1
        self.save_counts()

    def get_all_counts(self):
        return (
            {
                k: v
                for k, v in sorted(
                    self.counts.items(), key=lambda item: item[1]["count"], reverse=True
                )
            }
            if len(self.counts) != 0
            else {}
        )
