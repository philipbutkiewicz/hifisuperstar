#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import json
import os
import tempfile

from hifisuperstar.io.Logger import warn


def get_resource_path(res_type, res_param):
    storage_path = "storage" if res_type != "res" else "res"
    res_name = (
        f"{res_type}.{res_param}.json" if res_type != "res" else f"{res_param}.json"
    )
    return os.path.join(storage_path, res_name)


def write_json_atomic(path, data):
    """Writes JSON through a temporary file so a crash never leaves a truncated file behind."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, suffix=".tmp", delete=False
        ) as file:
            temporary_path = file.name
            json.dump(data, file)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def read_json_safe(path, default=None):
    """Returns the parsed JSON or `default` if the file is missing or corrupt (a corrupt file is left in place)."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        warn(None, f"Could not read '{path}' - {exc}")
        return default


def load_resource(res_type, res_param=None):
    res = read_json_safe(get_resource_path(res_type, res_param), {})

    return res or {}


def save_resource(res_type, res_param, data):
    write_json_atomic(get_resource_path(res_type, res_param), data)
