# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2022 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

from hifisuperstar.io.Resources import load_resource
from hifisuperstar.io.Resources import save_resource


class PlayCounter:

    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.counts = load_resource('counts', self.guild_id)

    def save_counts(self):
        save_resource('counts', self.guild_id, self.counts)

    def clear(self):
        self.counts = {}

    def count_playback(self, track):
        if not track['id'] in self.counts:
            self.counts[track['id']] = {
                'url': track['url'],
                'title': track['title'],
                'count': 0
            }

        self.counts[track['id']]['count'] += 1
        self.save_counts()

    def get_all_counts(self):
        return {k: v for k, v in
                sorted(self.counts.items(), key=lambda item: item[1]['count'], reverse=True)} if not len(
            self.counts) == 0 else {}
