#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import git
from flask import current_app


class Repo:

    @staticmethod
    def register(app):
        app.jinja_env.globals.update(git_repo_commit_hash=Repo.get_current_commit_hash)

    @staticmethod
    def get_current_commit_hash():
        path = current_app.config['BASE_APP_PATH']
        repo = git.Repo(path, search_parent_directories=True)
        return repo.head.object.hexsha
