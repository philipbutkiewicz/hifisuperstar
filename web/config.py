#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import os


class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', '')
    BASE_APP_PATH = '../'

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    @classmethod
    def validate(cls):
        if not cls.SECRET_KEY:
            raise ValueError(
                "FLASK_SECRET_KEY environment variable is not set. "
                "Set it to a long random string before starting the web server."
            )


class DevConfig(Config):
    TESTING = True
    DEBUG = True
    FLASK_ENV = 'development'


class ProdConfig(Config):
    TESTING = False
    DEBUG = False
    FLASK_ENV = 'production'
