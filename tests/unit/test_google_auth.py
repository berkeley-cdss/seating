"""Tests for the Google OAuth login flow.

The Google login flow lives alongside the Canvas login flow. The tests below
exercise the controller in /workspace/seating/server/controllers/auth_controllers.py
by patching the Google OAuth provider on `server.services.auth`. The Canvas
mock setup (MOCK_CANVAS=True) is untouched — Google login does not depend on
Canvas being live and should work the same in tests.
"""
from unittest.mock import patch, MagicMock

import pytest

from server import app
from server.models import User, db as sqlalchemy_db
import server.services.auth as auth_service
import server.controllers.auth_controllers as auth_controllers


@pytest.fixture()
def existing_user(db):
    user = User(
        name='Existing User',
        canvas_id='999000',
        email='existing@berkeley.edu',
        staff_offerings=['1'],
        student_offerings=['2'],
    )
    db.session.add(user)
    db.session.commit()
    return user


def _patch_google_enabled():
    """Force the controller to behave as if Google login is configured."""
    fake_provider = MagicMock()
    return [
        patch.object(auth_controllers, 'is_google_login_enabled', return_value=True),
        patch.object(auth_controllers, 'google_oauth_provider', fake_provider),
        patch.object(auth_service, 'google_oauth_provider', fake_provider),
    ], fake_provider


def test_login_page_shows_google_button_when_enabled(client, db):
    patches, _ = _patch_google_enabled()
    for p in patches:
        p.start()
    try:
        with patch('server.services.canvas.is_mock_canvas', return_value=False):
            response = client.get('/login/')
        assert response.status_code == 200
        body = response.data.decode('utf-8')
        assert 'Sign in with Canvas' in body
        assert 'Sign in with Google' in body
    finally:
        for p in patches:
            p.stop()


def test_login_page_no_google_when_disabled(client, db):
    with patch('server.services.canvas.is_mock_canvas', return_value=False), \
         patch.object(auth_controllers, 'is_google_login_enabled', return_value=False), \
         patch.object(auth_controllers, 'oauth_provider') as mock_oauth:
        mock_oauth.authorize.return_value = ('redirect', 302)
        client.get('/login/')
        # Without google enabled, login() should immediately call canvas authorize.
        assert mock_oauth.authorize.called


def test_google_login_redirects_to_google(client, db):
    patches, fake_provider = _patch_google_enabled()
    for p in patches:
        p.start()
    try:
        fake_provider.authorize.return_value = ('redirect-to-google', 302)
        response = client.get('/login/google/')
        assert fake_provider.authorize.called
        # Make sure a callback URL was provided
        _, kwargs = fake_provider.authorize.call_args
        assert 'callback' in kwargs
        assert '/authorized/google/' in kwargs['callback']
    finally:
        for p in patches:
            p.stop()


def test_google_login_disabled_redirects_home(client, db):
    with patch.object(auth_controllers, 'is_google_login_enabled', return_value=False):
        response = client.get('/login/google/')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')


def test_google_callback_authenticates_existing_user(client, existing_user):
    patches, fake_provider = _patch_google_enabled()
    for p in patches:
        p.start()
    try:
        fake_provider.authorized_response.return_value = {'access_token': 'tok'}
        userinfo = MagicMock()
        userinfo.data = {
            'sub': 'google-sub-1',
            'email': 'existing@berkeley.edu',
            'email_verified': True,
        }
        fake_provider.get.return_value = userinfo

        response = client.get('/authorized/google/')

        assert response.status_code == 302
        # User should now be linked to the google_id
        with app.app_context():
            user = User.query.filter_by(canvas_id='999000').one()
            assert user.google_id == 'google-sub-1'
    finally:
        for p in patches:
            p.stop()


def test_google_callback_rejects_unknown_email(client, db):
    patches, fake_provider = _patch_google_enabled()
    for p in patches:
        p.start()
    try:
        fake_provider.authorized_response.return_value = {'access_token': 'tok'}
        userinfo = MagicMock()
        userinfo.data = {
            'sub': 'google-sub-999',
            'email': 'stranger@berkeley.edu',
            'email_verified': True,
        }
        fake_provider.get.return_value = userinfo

        before = User.query.count()
        response = client.get('/authorized/google/', follow_redirects=False)
        after = User.query.count()

        # Must not create a new user.
        assert before == after
        assert response.status_code == 302
    finally:
        for p in patches:
            p.stop()


def test_google_callback_enforces_hosted_domain(client, existing_user):
    patches, fake_provider = _patch_google_enabled()
    for p in patches:
        p.start()
    try:
        fake_provider.authorized_response.return_value = {'access_token': 'tok'}
        userinfo = MagicMock()
        userinfo.data = {
            'sub': 'google-sub-1',
            'email': 'existing@gmail.com',
            'email_verified': True,
            'hd': 'gmail.com',
        }
        fake_provider.get.return_value = userinfo

        old = app.config.get('GOOGLE_HOSTED_DOMAINS')
        app.config['GOOGLE_HOSTED_DOMAINS'] = 'berkeley.edu'
        try:
            response = client.get('/authorized/google/', follow_redirects=False)
        finally:
            app.config['GOOGLE_HOSTED_DOMAINS'] = old

        assert response.status_code == 302
        # Existing user should not have been linked to a disallowed domain.
        with app.app_context():
            user = User.query.filter_by(canvas_id='999000').one()
            assert user.google_id is None
    finally:
        for p in patches:
            p.stop()


def test_google_callback_unverified_email_rejected(client, existing_user):
    patches, fake_provider = _patch_google_enabled()
    for p in patches:
        p.start()
    try:
        fake_provider.authorized_response.return_value = {'access_token': 'tok'}
        userinfo = MagicMock()
        userinfo.data = {
            'sub': 'google-sub-1',
            'email': 'existing@berkeley.edu',
            'email_verified': False,
        }
        fake_provider.get.return_value = userinfo

        response = client.get('/authorized/google/', follow_redirects=False)
        assert response.status_code == 302
        with app.app_context():
            user = User.query.filter_by(canvas_id='999000').one()
            assert user.google_id is None
    finally:
        for p in patches:
            p.stop()
