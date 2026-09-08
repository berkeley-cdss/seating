from flask import request, jsonify, abort, redirect, url_for, render_template
import server.services.canvas as canvas_client

from server.controllers import dev_login_module
from server.services.auth import oauth_provider
from server.services.canvas.fake_data import FAKE_COURSES, FAKE_ENROLLMENTS, FAKE_USERS


def _mock_user_roster():
    """
    The seed users, with the courses they are enrolled in, so that whoever is
    running a dev server can tell the staff accounts from the student ones
    without reading the fixtures.
    """
    roster = []
    for user_id, user in FAKE_USERS.items():
        courses = []
        for course_id, enrollment in FAKE_ENROLLMENTS.get(user_id, {}).items():
            course = FAKE_COURSES.get(course_id, {})
            roles = sorted({e['type'] for e in enrollment.get('enrollments', [])})
            courses.append({'name': course.get('name', course_id), 'roles': roles})
        roster.append({
            'id': user_id,
            'name': user['name'],
            'email': user.get('email', ''),
            'courses': sorted(courses, key=lambda c: c['name']),
        })
    return sorted(roster, key=lambda u: u['name'])


@dev_login_module.route('/', methods=['GET', 'POST'])
def dev_login_page():
    if canvas_client.is_mock_canvas():
        from server.forms import DevLoginForm
        form = DevLoginForm()
        if form.validate_on_submit():
            if form.user_id.data:
                return oauth_provider.authorize(
                    callback=url_for('auth.authorized'),
                    state=None,
                    user_id=form.user_id.data,
                    _external=True, _scheme="http")
            else:
                abort(500, 'Invalid dev user')
        return render_template('dev_login.html.j2', mock_users=_mock_user_roster(),
                               form=form, title="Dev Login")
    return redirect(url_for('index'))


@dev_login_module.route('/oauth2/auth/', methods=['GET'])
def mock_authorize():
    redirect_uri = request.args.get('redirect_uri', None)
    state = request.args.get('state', '')
    user_id = request.args.get('user_id', None)
    if redirect_uri:
        sep = '&' if '?' in redirect_uri else '?'
        full_redirect_uri = \
            f"{redirect_uri}{sep}code={user_id}&state={state}"
        return redirect(full_redirect_uri)
    else:
        abort(400, 'Invalid redirect_uri: {}'.format(redirect_uri))


@dev_login_module.route('/oauth2/token/', methods=['POST'])
def mock_token():
    user_id = request.form.get('code')
    if not user_id:
        abort(400, 'Invalid dev user')

    mock_response = {
        'access_token': 'dev_access_token',
        'token_type': 'Bearer',
        'user': FAKE_USERS[str(user_id)],
        'canvas_region': 'us-east-1',
        'refresh_token': 'dev_refresh_token',
        'expires_in': 3600
    }
    return jsonify(mock_response)
