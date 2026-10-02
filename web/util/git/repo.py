#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import os

import git
from flask import current_app


class Repo:
    @staticmethod
    def register(app):
        app.jinja_env.globals.update(git_repo_commit_hash=Repo.get_current_commit_hash)

    @staticmethod
    def get_current_commit_hash():
        if commit := os.environ.get("GIT_COMMIT_SHA"):
            return commit

        path = current_app.config["BASE_APP_PATH"]
        try:
            repo = git.Repo(path, search_parent_directories=True)
            return repo.head.object.hexsha
        except git.GitError:
            return "unknown"
