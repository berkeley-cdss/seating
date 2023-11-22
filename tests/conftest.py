import os

import pytest
import responses
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from server import app as flask_app
from server.models import db as sqlalchemy_db


@pytest.fixture()
def app():
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


@pytest.fixture()
def mocker():
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture()
def driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=options)
    yield driver
    driver.close()


@pytest.fixture()
def get_authed_driver(driver):
    from selenium.webdriver.common.by import By

    def _get_authed_driver(some_user_id):
        driver.get('http://localhost:5000/')
        assert 'Login' in driver.title
        user_id_input = driver.find_element(By.CSS_SELECTOR, '#user_id')
        assert user_id_input is not None
        user_id_input.send_keys(some_user_id)
        form_submit_btn = driver.find_element(By.CSS_SELECTOR, '#submit')
        assert form_submit_btn is not None
        form_submit_btn.click()
        return driver

    yield _get_authed_driver


@pytest.fixture()
def seeded_db(app):
    import flask_fixtures as ff

    with app.app_context():
        sqlalchemy_db.drop_all()
        sqlalchemy_db.create_all()

        seed_dir_paths = [os.path.join(app.config.get('BASE_DIR'), d)
                          for d in app.config.get('FIXTURES_DIRS')]
        seed_files_names = []
        seed_file_formats = set(['.yaml', '.yml', '.json'])

        for d in seed_dir_paths:
            for file in os.listdir(d):
                if not any([file.endswith(form) for form in seed_file_formats]):
                    continue
                seed_files_names.append(file)

        sqlalchemy_db.create_all()
        sqlalchemy_db.session.rollback()

        for filename in seed_files_names:
            ff.load_fixtures_from_file(sqlalchemy_db, filename, seed_dir_paths)

        yield sqlalchemy_db

        sqlalchemy_db.session.expunge_all()
        sqlalchemy_db.drop_all()
