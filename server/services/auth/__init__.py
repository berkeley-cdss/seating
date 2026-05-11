from flask import redirect, request, session, url_for

import server.services.canvas as canvas_client
from flask_login import LoginManager
from flask_oauthlib.client import OAuth
from .scope import scopes

from server import app

login_manager = LoginManager(app=app)

oauth = OAuth()

canvas_server_url = app.config.get('CANVAS_SERVER_URL')
consumer_key = app.config.get('CANVAS_CLIENT_ID')
consumer_secret = app.config.get('CANVAS_CLIENT_SECRET')
dev_oauth_server_url = app.config.get('SERVER_BASE_URL')

oauth_provider = None

if not canvas_client.is_mock_canvas():
    oauth_provider = oauth.remote_app(
        'seating',
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        base_url=canvas_server_url,
        request_token_url=None,
        access_token_method='POST',
        access_token_url=canvas_server_url + 'login/oauth2/token',
        authorize_url=canvas_server_url + 'login/oauth2/auth',
        request_token_params={'scope': ' '.join(scopes)},
    )
else:
    # dev login uses HTTP so we need to allow that for OAuth2
    import os
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    oauth_provider = oauth.remote_app(
        'seating_dev',
        consumer_key='development_key',
        consumer_secret='development_secret',
        base_url=dev_oauth_server_url,
        request_token_url=None,
        access_token_method='POST',
        access_token_url=dev_oauth_server_url + 'dev_login/oauth2/token/',
        authorize_url=dev_oauth_server_url + 'dev_login/oauth2/auth/',
    )


@oauth_provider.tokengetter
def get_access_token(token=None):
    return session.get('access_token')


google_client_id = app.config.get('GOOGLE_CLIENT_ID')
google_client_secret = app.config.get('GOOGLE_CLIENT_SECRET')

google_oauth_provider = None

if google_client_id and google_client_secret:
    google_oauth_provider = oauth.remote_app(
        'google',
        consumer_key=google_client_id,
        consumer_secret=google_client_secret,
        request_token_params={
            'scope': 'openid email profile',
        },
        base_url='https://www.googleapis.com/oauth2/v3/',
        request_token_url=None,
        access_token_method='POST',
        access_token_url='https://oauth2.googleapis.com/token',
        authorize_url='https://accounts.google.com/o/oauth2/auth',
    )

    @google_oauth_provider.tokengetter
    def get_google_access_token(token=None):
        return session.get('google_access_token')


def is_google_login_enabled() -> bool:
    return google_oauth_provider is not None


@login_manager.user_loader
def load_user(user_id):
    from server.models import User
    return User.query.get(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    session['after_login'] = request.url
    return redirect(url_for('auth.login'))
