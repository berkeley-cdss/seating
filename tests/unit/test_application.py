"""Building the app: create_app, the app gunicorn serves, and what each environment turns on."""
import importlib
import logging

import pytest
from canvasapi.exceptions import InvalidAccessToken

import config
import server
import server.application as application
from server.typings.exception import EnvironmentalVariableMissingError


@pytest.mark.parametrize('env, config_class', [
    ('production', config.ProductionConfig),
    ('staging', config.StagingConfig),
    ('development', config.DevelopmentConfig),
    ('testing', config.TestingConfig),
    ('Testing', config.TestingConfig),
])
def test_flask_env_picks_the_config(monkeypatch, env, config_class):
    monkeypatch.setenv('FLASK_ENV', env)
    assert application.config_for_environment() is config_class


def test_flask_env_defaults_to_development(monkeypatch):
    monkeypatch.delenv('FLASK_ENV', raising=False)
    assert application.config_for_environment() is config.DevelopmentConfig


def test_unknown_flask_env_is_refused(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'prod')
    with pytest.raises(EnvironmentalVariableMissingError):
        application.config_for_environment()


def test_without_a_config_the_environment_picks_one(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'testing')
    assert application.create_app().config['FLASK_ENV'] == 'testing'


def test_each_app_has_its_own_config():
    first = application.create_app(config.TestingConfig)
    first.config['MOCK_CANVAS'] = False
    assert application.create_app(config.TestingConfig).config['MOCK_CANVAS'] is True


def test_flask_app_server_finds_the_factory():
    # `flask --app server` calls server.create_app(), as FLASK_APP=server is set in places
    assert server.create_app(config.TestingConfig).config['FLASK_ENV'] == 'testing'


def test_gunicorn_app(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'testing')
    import server.main
    main = importlib.reload(server.main)
    assert main.app.config['FLASK_ENV'] == 'testing'
    assert 'views.offerings' in {rule.endpoint for rule in main.app.url_map.iter_rules()}


def test_every_app_logs_info_to_stderr_once():
    # whichever way the app is loaded (server.main, or `flask --app server`)
    for _ in range(3):
        app = server.create_app(config.TestingConfig)
    assert app.logger.isEnabledFor(logging.INFO)
    assert sum(getattr(handler, 'seating', False) for handler in app.logger.handlers) == 1


def test_a_bad_photo_cache_life_stops_the_app_from_starting(monkeypatch):
    monkeypatch.setenv('C1C_PHOTO_CACHE_LIFE', '90d')
    with pytest.raises(ValueError):
        config.TestingConfig()


@pytest.fixture
def sentry_inits(monkeypatch):
    import sentry_sdk
    calls = []
    monkeypatch.setattr(sentry_sdk, 'init', lambda **kwargs: calls.append(kwargs))
    return calls


@pytest.mark.parametrize('config_class', [config.StagingConfig, config.ProductionConfig])
def test_sentry_reports_from_staging_and_production(monkeypatch, sentry_inits, config_class):
    monkeypatch.setenv('DATABASE_URL', 'sqlite://')
    monkeypatch.setenv('SECRET_KEY', 'test')
    app_config = config_class()
    application.create_app(app_config)
    assert [call['environment'] for call in sentry_inits] == [app_config.FLASK_ENV]


@pytest.mark.parametrize('config_class', [config.DevelopmentConfig, config.TestingConfig])
def test_sentry_is_off_in_development_and_testing(sentry_inits, config_class):
    application.create_app(config_class)
    assert sentry_inits == []


def test_expired_canvas_token_sends_you_to_log_in(app):
    def expired():
        raise InvalidAccessToken('expired')

    app.add_url_rule('/expired-token/', 'expired_token', expired)
    response = app.test_client().get('/expired-token/')
    assert response.status_code == 302
    assert response.location == '/login'
