# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2022 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import logging


def log_init():
    logging.basicConfig(
        level=logging.INFO,
        format='(%(asctime)s) [%(name)s:%(levelname)s] %(message)s',
        datefmt='%m/%d/%Y %I:%M:%S %p',
        handlers=[
            logging.FileHandler('app.log'),
            logging.StreamHandler()
        ]
    )


def build_message(module, message, guild=None):
    guild_str = f" <{guild.id}, '{guild.name}'> " if guild else ' '
    return f"[{type(module).__name__ if module is not None else 'App'}]{guild_str}{message}"


def info(module, message, guild=None):
    logging.info(build_message(module, message, guild))


def error(module, message, guild=None):
    logging.error(build_message(module, message, guild))


def warn(module, message, guild=None):
    logging.warning(build_message(module, message, guild))
