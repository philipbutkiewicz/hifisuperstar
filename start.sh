#!/bin/bash

# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

export FLASK_ENV=production
export FLASK_APP=web/app.py
uv run flask run > flask.log &
uv run app.py