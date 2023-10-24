import os

import pytest

from server import app as flask_app
from server.models import db as sqlalchemy_db


@pytest.fixture()
def app():
    flask_app.config.update({
        'FLASK_ENV': 'testing',
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' +
        os.path.join(flask_app.config["BASE_DIR"], 'test.db')
    })

    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()


@pytest.fixture()
def db(app):
    with app.app_context():
        sqlalchemy_db.drop_all()
        sqlalchemy_db.create_all()

        yield sqlalchemy_db

        sqlalchemy_db.session.remove()
        sqlalchemy_db.drop_all()
