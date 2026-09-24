#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#


import typing


class Events:
    events: typing.ClassVar = []

    @staticmethod
    def add_event(event_name, event_func):
        Events.events.append({"name": event_name, "func": event_func})

    @staticmethod
    async def run_event(event_name, **args):
        matches = [item for item in Events.events if item["name"] == event_name]
        for match in matches:
            await match["func"](**args)
