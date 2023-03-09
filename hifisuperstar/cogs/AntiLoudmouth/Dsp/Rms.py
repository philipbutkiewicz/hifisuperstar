#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import numpy as np
import wave
import math


def get_chunk_log_rms(chunk):
    log_rms = 0

    if len(chunk) > 0:
        deserialized_bytes = np.frombuffer(chunk, dtype=np.int8)
        mean = sum(np.absolute(deserialized_bytes)) / len(chunk)
        rms = np.sqrt(np.mean(mean**2))
        log_rms = 20 * math.log10(rms)

    return np.round(np.absolute(log_rms), 1)


def get_avg_log_rms_fromfile(fname):
    avg_rms = 0

    with wave.open(fname, 'rb') as f:
        data = f.readframes(1024)

        log_rms_values = []
        while len(data) > 0:
            data = f.readframes(1024)

            log_rms = get_chunk_log_rms(data)
            log_rms_values.append(log_rms)

        avg_rms = np.average(log_rms_values)

    return np.round(avg_rms, 1)
