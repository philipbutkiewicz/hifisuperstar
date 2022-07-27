#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2022 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

class Config:
    SECRET_KEY = ''
    BASE_APP_PATH = '../'


class DevConfig(Config):
    TESTING = True
    DEBUG = True
    FLASK_ENV = 'development'


class ProdConfig(Config):
    TESTING = False
    DEBUG = False
    FLASK_ENV = 'production'
