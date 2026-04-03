# 
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

from flask import Flask
from flask import render_template
from util.git.repo import Repo
from routes import home_bp
from routes import playlists_bp

# Register app
app = Flask(__name__)
app.config.from_object('config.ProdConfig')

# Register utils
Repo.register(app)

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('errors/500.html'), 404


# Register routes
app.register_blueprint(home_bp)
app.register_blueprint(playlists_bp)

# Run the app
if __name__ == '__main__':
    app.run()

