#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#


def get_guild_config(config, section, guild_id):
    defaults = config.get(section, {})
    overrides = config.get("Guilds", {}).get(str(guild_id), {}).get(section, {})

    def merge(base, changes):
        result = base.copy()
        for key, value in changes.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = merge(result[key], value)
            else:
                result[key] = value
        return result

    return merge(defaults, overrides)
