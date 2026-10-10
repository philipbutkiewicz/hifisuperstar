#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import logging
import sys

from loguru import logger

_LOG_FORMAT = (
    "<green>{time:MM/DD/YYYY hh:mm:ss A}</green> [<level>{level}</level>] {message}"
)


class _DiscordLogHandler(logging.Handler):
    """Forwards discord.py's own log records (voice close codes, reconnects) into the app log."""

    def emit(self, record):
        message = f"[{record.name}] {record.getMessage()}"
        if record.exc_info:
            logger.opt(exception=record.exc_info).log(record.levelname, message)
        else:
            logger.log(record.levelname, message)


def log_init():
    logger.remove()
    logger.add(sys.stdout, level="INFO", format=_LOG_FORMAT, colorize=True)
    logger.add(
        "app.log",
        level="INFO",
        format=_LOG_FORMAT,
        encoding="utf-8",
        rotation="10 MB",
        retention=5,
    )

    discord_logger = logging.getLogger("discord")
    if not any(isinstance(h, _DiscordLogHandler) for h in discord_logger.handlers):
        discord_logger.addHandler(_DiscordLogHandler())
    discord_logger.setLevel(logging.INFO)


def build_message(module, message, guild=None):
    guild_str = f" <{guild.id}, '{guild.name}'> " if guild else " "
    return f"[{type(module).__name__ if module is not None else 'App'}]{guild_str}{message}"


def info(module, message, guild=None):
    logger.info(build_message(module, message, guild))


def error(module, message, guild=None):
    logger.error(build_message(module, message, guild))


def warn(module, message, guild=None):
    logger.warning(build_message(module, message, guild))