"""
Staging and production sign sessions with the SECRET_KEY they are deployed with, and refuse to
start without one rather than fall back to a key written in the code.
"""
import pytest
from flask import Flask

import config
from server.typings.exception import EnvironmentalVariableMissingError

DEPLOYED_CONFIGS = [config.StagingConfig, config.ProductionConfig]


@pytest.mark.parametrize('config_class', DEPLOYED_CONFIGS)
def test_deployments_use_the_secret_key_from_the_environment(config_class, monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'from-the-environment')
    monkeypatch.setenv('DATABASE_URL', 'postgres://user@host/db')
    app = Flask(__name__)
    app.config.from_object(config_class())
    assert app.config['SECRET_KEY'] == 'from-the-environment'


@pytest.mark.parametrize('config_class', DEPLOYED_CONFIGS)
def test_deployments_refuse_to_start_without_a_secret_key(config_class, monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    with pytest.raises(EnvironmentalVariableMissingError):
        config_class().SECRET_KEY
