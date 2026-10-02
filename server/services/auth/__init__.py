from flask import redirect, request, session, url_for

import server.services.canvas as canvas_client
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth
from .scope import scopes

from server import app

login_manager = LoginManager(app=app)

oauth = OAuth(app)

canvas_server_url = app.config.get('CANVAS_SERVER_URL')
consumer_key = app.config.get('CANVAS_CLIENT_ID')
consumer_secret = app.config.get('CANVAS_CLIENT_SECRET')
dev_oauth_server_url = app.config.get('SERVER_BASE_URL')


def get_access_token():
    """
    Supplies the stored Canvas token to Authlib when the client is used to call
    the remote API. Authlib expects a token dict rather than a bare string.
    """
    access_token = session.get('access_token')
    return {'access_token': access_token, 'token_type': 'Bearer'} if access_token else None


if not canvas_client.is_mock_canvas():
    oauth_provider = oauth.register(
        'seating',
        client_id=consumer_key,
        client_secret=consumer_secret,
        api_base_url=canvas_server_url,
        access_token_url=canvas_server_url + 'login/oauth2/token',
        authorize_url=canvas_server_url + 'login/oauth2/auth',
        # Canvas expects the client credentials in the POST body, not a Basic auth header
        client_kwargs={
            'scope': ' '.join(scopes),
            'token_endpoint_auth_method': 'client_secret_post',
        },
        fetch_token=get_access_token,
    )
else:
    # dev login uses HTTP so we need to allow that for OAuth2
    import os
    os.environ['AUTHLIB_INSECURE_TRANSPORT'] = '1'
    oauth_provider = oauth.register(
        'seating_dev',
        client_id='development_key',
        client_secret='development_secret',
        api_base_url=dev_oauth_server_url,
        access_token_url=dev_oauth_server_url + 'dev_login/oauth2/token/',
        authorize_url=dev_oauth_server_url + 'dev_login/oauth2/auth/',
        client_kwargs={'token_endpoint_auth_method': 'client_secret_post'},
        fetch_token=get_access_token,
    )


@login_manager.user_loader
def load_user(user_id):
    from server.models import db, User
    return db.session.get(User, user_id)


@login_manager.unauthorized_handler
def unauthorized():
    session['after_login'] = request.url
    return redirect(url_for('auth.login'))
