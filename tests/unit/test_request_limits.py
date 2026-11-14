"""
Slow or large requests can't tie up the app: requests to C1C time out, and a request larger than
MAX_CONTENT_LENGTH is refused with 413 before its upload is read.
"""
import io

import pytest
import requests

import config
import server.services.c1c as c1c

IMPORT_URL = '/offerings/1234567/exams/midterm1/students/import/'


@pytest.mark.app_config(MOCK_C1C=False)
def test_a_slow_c1c_shows_the_placeholder_photo(app, monkeypatch):
    calls = []

    def time_out(method, url, **kwargs):
        calls.append(kwargs)
        raise requests.Timeout()
    monkeypatch.setattr(requests, 'request', time_out)
    with app.app_context():
        client = c1c.C1C(None, 'https://c1c.example.edu', 'user', 'password')
        assert client.get_student_photo('12345678') is None
    assert calls[0]['timeout'] == c1c.TIMEOUT


def test_uploads_over_the_limit_are_refused(seeded_db, login_as):
    too_big = io.BytesIO(b'x' * (config.ConfigBase.MAX_CONTENT_LENGTH + 1))
    response = login_as(1).post(IMPORT_URL, data={'file': (too_big, 'students.csv')},
                                content_type='multipart/form-data')
    assert response.status_code == 413
