#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2022 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import os
import json


def get_resource_path(res_type, res_param):
    storage_path = 'storage' if res_type != 'res' else 'res'
    res_name = f"{res_type}.{res_param}.json" if res_type != 'res' else f"{res_param}.json"
    return os.path.join(storage_path, res_name)


def load_resource(res_type, res_param=None):
    res_path = get_resource_path(res_type, res_param)

    if not os.path.exists(res_path):
        return {}

    res = json.loads(open(res_path, encoding='utf-8').read())
    if not res:
        return {}

    return res


def save_resource(res_type, res_param, data):
    res_path = get_resource_path(res_type, res_param)

    with open(res_path, 'w', encoding='utf-8') as file:
        json.dump(data, file)
