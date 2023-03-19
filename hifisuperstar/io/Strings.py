# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import zlib
import hashlib
import random

allowed_chars_regex = '^[a-zA-Z0-9\~\`\!\@\#\$\%\^\&\*\(\)\-\_\=\+\[\]\{\}\|\;\'\:\"\,\.\/\<\>\?\ ]+$'


def str_rand_crc32():
    return hex(zlib.crc32(random.randbytes(64)))


def str_rand_sha256():
    return hashlib.sha256(random.randbytes(64)).hexdigest()


def str_hash_crc32(string):
    return hex(zlib.crc32(string.encode('utf-8')))


def str_hash_sha256(string):
    return hashlib.sha256(string.encode('utf-8')).hexdigest()
