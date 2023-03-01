#!/bin/bash

# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

export FLASK_ENV=production
export FLASK_APP=web/app.py
flask run > flask.log &
python app.py