from flask import redirect, request, session, url_for
from flask_login import LoginManager, login_user, logout_user
from flask_oauthlib.client import OAuth
from oauth2client.contrib.flask_util import UserOAuth2


from server import app
from server.models import db, User
import server.utils.canvas as canvas_client
from server.utils.stub import DEV_OAUTH_RESP

login_manager = LoginManager(app=app)

oauth = OAuth()

server_url = app.config.get('CANVAS_SERVER_URL')
consumer_key = app.config.get('CANVAS_CLIENT_ID')
consumer_secret = app.config.get('CANVAS_CLIENT_SECRET')

canvas_oauth = oauth.remote_app(
    'seating',
    consumer_key=consumer_key,
    consumer_secret=consumer_secret,
    base_url=server_url,
    request_token_url=None,
    access_token_method='POST',
    access_token_url=server_url + 'login/oauth2/token',
    authorize_url=server_url + 'login/oauth2/auth',
)


@canvas_oauth.tokengetter
def get_access_token(token=None):
    return session.get('access_token')


google_oauth = UserOAuth2(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    session['after_login'] = request.url
    return redirect(url_for('login'))


@app.route('/login/')
def login():
    if app.config['FLASK_ENV'] == 'development':
        return redirect(url_for('authorized'))
    return canvas_oauth.authorize(callback=url_for('authorized', _external=True, _scheme='https'))


@app.route('/authorized/')
def authorized():
    if app.config['FLASK_ENV'] == 'development':
        resp = DEV_OAUTH_RESP
    else:
        resp = canvas_oauth.authorized_response()

    if resp is None:
        return 'Access denied: {}'.format(request.args.get('error', 'unknown error'))
    session['access_token'] = resp['access_token']
    user_info = resp['user']

    user = canvas_client.get_user(user_info['id'])
    staffing = []
    courses_raw = canvas_client.get_user_courses(user)
    for c in courses_raw:
        # c may be a dict or a Course object
        c_dic = c.__dict__ if hasattr(c, '__dict__') else c
        if 'id' not in c_dic or 'enrollments' not in c_dic:
            continue
        for e in c_dic['enrollments']:
            if e["type"] == 'ta' or e["type"] == 'teacher':
                staffing.append(str(c_dic['id']))
                break

    user_model = User.query.filter_by(canvas_id=user_info['id']).one_or_none()
    if not user_model:
        user_model = User(canvas_id=user_info['id'], staffing=staffing)
        db.session.add(user_model)
    else:
        user_model.staffing = staffing
    db.session.commit()

    login_user(user_model, remember=True)
    after_login = session.pop('after_login', None) or url_for('index')
    return redirect(after_login)


@app.route('/logout/')
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('index'))
