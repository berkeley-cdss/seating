from flask import redirect, request, session, url_for
from flask_login import LoginManager, login_required, login_user, logout_user
from flask_oauthlib.client import OAuth, OAuthException
from oauth2client.contrib.flask_util import UserOAuth2
from werkzeug import security
from canvasapi import Canvas

from server import app
from server.models import db, User, Student, SeatAssignment

login_manager = LoginManager(app=app)

oauth = OAuth()

server_url = app.config.get('CANVAS_SERVER_URL')
consumer_key = app.config.get('CANVAS_CLIENT_ID')
consumer_secret = app.config.get('CANVAS_CLIENT_SECRET')
canvas_course_id = app.config.get('CANVAS_COURSE_ID')

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
    return canvas_oauth.authorize(callback=url_for('authorized', _external=True, _scheme='https'))

@app.route('/authorized/')
def authorized():
    resp = canvas_oauth.authorized_response()
    if resp is None:
        return 'Access denied: {}'.format(request.args.get('error', 'unknown error'))

    # check if user is enrolled in course
    session['access_token'] = resp['access_token']
    user_info = resp['user']
    canvas = Canvas(server_url, session['access_token'])
    user = canvas.get_user(user_info['id'])
    course_raw = None
    for c in user.get_courses(enrollment_status='active'):
        if not hasattr(c, 'id'):
            continue
        if str(c.id) == canvas_course_id:
            course_raw = c
            break
    if not course_raw:
        return 'No enrollment info found for this user in course id {}.'.format(canvas_course_id)
    course = {}
    course['id'] = course_raw.id
    course['name'] = course_raw.name
    course['sis_course_id'] = course_raw.sis_course_id
    course['course_code'] = course_raw.course_code
    session['course'] = course

    # check if user is staff
    is_staff = False
    for e in course_raw.enrollments:
        if e["type"] == 'ta' or e["type"] == 'teacher':
            is_staff = True
            break
    if not is_staff:
        return 'Access denied. Not a staff member in course id {}.'.format(canvas_course_id)

    print("Nice! You're a staff member in course id {}. Continuing...".format(canvas_course_id))
    
    # login_user(user, remember=True)
    after_login = session.pop('after_login', None) or url_for('index')
    return redirect(after_login)

@app.route('/logout/')
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('index'))
