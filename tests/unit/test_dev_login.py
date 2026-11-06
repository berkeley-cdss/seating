from urllib.parse import parse_qs, urlsplit

import pytest

import config
from server.controllers.dev_login_controllers import _mock_user_roster


class TestEnvironmentGating:
    """
    The fake Canvas - and with it the dev login page - is the default outside
    staging and production, and must never be reachable inside them.
    """

    def test_staging_and_production_never_mock_canvas(self, monkeypatch):
        monkeypatch.setenv('MOCK_CANVAS', 'true')
        assert config.StagingConfig().MOCK_CANVAS is False
        assert config.ProductionConfig().MOCK_CANVAS is False

    def test_development_and_testing_mock_canvas(self, monkeypatch):
        monkeypatch.delenv('MOCK_CANVAS', raising=False)
        assert config.DevelopmentConfig().MOCK_CANVAS is True
        assert config.TestingConfig().MOCK_CANVAS is True

    def test_development_can_opt_out_of_the_fake_canvas(self, monkeypatch):
        # the environment is read when a config is made, so no reloading is needed
        monkeypatch.setenv('MOCK_CANVAS', 'false')
        assert config.DevelopmentConfig().MOCK_CANVAS is False
        # ...but staging and production do not read the environment at all.
        assert config.StagingConfig().MOCK_CANVAS is False


class TestMockUserRoster:
    def test_lists_the_seeded_users_by_name(self):
        roster = _mock_user_roster()
        assert [user['name'] for user in roster] == [
            'Jimmy Xu', 'Lavender Angela', 'Sharon Lovera', 'Yu Long']

    def test_shows_the_roles_that_decide_what_a_user_can_do(self):
        yu_long = next(u for u in _mock_user_roster() if u['name'] == 'Yu Long')
        assert yu_long['id'] == '123456'
        assert yu_long['email'] == 'long_yu@berkeley.edu'
        roles = {course['name']: course['roles'] for course in yu_long['courses']}
        assert roles['Introduction to Software Engineering (Fall 2023)'] == ['ta']
        assert roles['Computer Architecture (Fall 2022)'] == ['student']


class TestDevLoginPage:
    def test_login_lands_on_the_dev_login_page(self, client):
        response = client.get('/login/')
        assert response.status_code == 302
        assert '/dev_login/' in response.headers['Location']

    def test_page_offers_every_seeded_user(self, client):
        response = client.get('/dev_login/')
        assert response.status_code == 200
        for name in ('Jimmy Xu', 'Lavender Angela', 'Sharon Lovera', 'Yu Long'):
            assert name.encode() in response.data
        assert response.data.count(b'name="user_id" value=') == 4

    @pytest.mark.app_config(WTF_CSRF_ENABLED=False)  # these tests are not about the CSRF token
    def test_a_pasted_id_is_trimmed(self, client):
        # Copying an ID out of a spreadsheet brings whitespace with it.
        response = client.post('/dev_login/', data={'user_id': '  345678\n'})
        assert response.status_code == 302
        assert 'user_id=345678' in response.headers['Location']

    @pytest.mark.app_config(WTF_CSRF_ENABLED=False)  # these tests are not about the CSRF token
    def test_an_unknown_id_is_explained_rather_than_crashing(self, client):
        response = client.post('/dev_login/', data={'user_id': '999999'}, follow_redirects=True)
        assert response.status_code == 200
        assert b'No seeded user has Canvas ID 999999' in response.data

    @pytest.mark.app_config(WTF_CSRF_ENABLED=False)  # these tests are not about the CSRF token
    def test_a_missing_id_is_reported(self, client):
        response = client.post('/dev_login/', data={'user_id': ''}, follow_redirects=True)
        assert response.status_code == 200
        assert b'This field is required' in response.data

    def test_the_token_endpoint_rejects_an_unknown_user(self, client):
        # Nothing reaches this with a bad id now, but it should not 500 if it does.
        assert client.post('/dev_login/oauth2/token/', data={'code': '999999'}).status_code == 400
        assert client.post('/dev_login/oauth2/token/', data={}).status_code == 400
        assert client.post('/dev_login/oauth2/token/', data={'code': '123456'}).status_code == 200


@pytest.mark.app_config(MOCK_CANVAS=False)
class TestRealCanvas:
    def test_dev_login_page_is_hidden(self, client):
        response = client.get('/dev_login/')
        assert response.status_code == 302
        assert '/dev_login' not in response.headers['Location']

    def test_login_redirects_to_real_canvas(self, app, client):
        response = client.get('/login/')
        assert response.status_code == 302
        location = urlsplit(response.headers['Location'])
        assert f'{location.scheme}://{location.netloc}{location.path}' == \
            app.config['CANVAS_SERVER_URL'] + 'login/oauth2/auth'
        assert parse_qs(location.query)['redirect_uri'] == ['https://localhost/authorized/']
