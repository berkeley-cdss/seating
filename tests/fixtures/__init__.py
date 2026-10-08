import importlib
import json
import os

from server import app
from server.models import db


def _read_fixture_file(filepath):
    _, ext = os.path.splitext(filepath)
    with open(filepath) as f:
        if ext in ('.yaml', '.yml'):
            import yaml
            return yaml.safe_load(f)
        return json.load(f)


def _load_fixtures_from_file(filepath):
    """
    Loads a list of ``{"model": ..., "records": [...]}`` entries into the database.

    This used to be provided by the (unmaintained) flask-fixtures package, which
    is incompatible with Flask >= 2.3.
    """
    for fixture in _read_fixture_file(filepath):
        module_name, class_name = fixture['model'].rsplit('.', 1)
        model = getattr(importlib.import_module(module_name), class_name)
        for fields in fixture['records']:
            db.session.add(model(**fields))
    db.session.commit()


def seed_db():
    seed_dir_paths = [os.path.join(app.config.get('BASE_DIR'), d)
                      for d in app.config.get('FIXTURES_DIRS')]
    seed_file_paths = []
    seed_file_formats = set(['.yaml', '.yml', '.json'])

    for d in seed_dir_paths:
        for file in os.listdir(d):
            if not any([file.endswith(form) for form in seed_file_formats]):
                continue
            seed_file_paths.append(os.path.join(d, file))

    for filepath in seed_file_paths:
        _load_fixtures_from_file(filepath)
