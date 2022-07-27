# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2022 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

from flask import render_template


class HomeController:

    @staticmethod
    def index():
        return render_template('home/index.html')
