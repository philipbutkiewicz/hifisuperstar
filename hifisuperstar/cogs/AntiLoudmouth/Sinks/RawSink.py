# RawSink is a py-cord-only concept (discord.sinks). Stubbed for discord.py compatibility.

class RawSink:
    def __init__(self):
        self.encoding = 'raw'
        self.ctx = None
        self.audio_received = None
        self.audio_data = {}

    def write(self, data, user):
        if self.audio_received is not None:
            self.audio_received(user, data, self.ctx)

