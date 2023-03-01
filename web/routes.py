# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

from flask import Blueprint
from controllers.PlaylistController import PlaylistController
from controllers.HomeController import HomeController


home_bp = Blueprint('home', __name__)
home_bp.route('/', methods=['GET'])(HomeController().index)

playlists_bp = Blueprint('playlists', __name__)
playlists_bp.route('/playlists/<guild_id>', methods=['GET'])(PlaylistController().list)
playlists_bp.route('/playlists/<guild_id>/<name>', methods=['GET'])(PlaylistController().show)
