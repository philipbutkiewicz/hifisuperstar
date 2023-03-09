from discord.sinks import Filters, Sink, default_filters

class RawSink(Sink):

    def __init__(self, *, filters=None):
        if filters is None:
            filters = default_filters
        self.filters = filters
        Filters.__init__(self, **self.filters)

        self.encoding = "raw"
        self.ctx = None
        self.audio_received = None
        self.audio_data = {}

    def write(self, data, user):
        if self.audio_received is not None:
            self.audio_received(user, data, self.ctx)
