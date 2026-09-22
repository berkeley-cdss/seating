from flask import flash, redirect, render_template, request, session, url_for
from flask_login import login_user, logout_user, login_required
import server.services.canvas as canvas_client

from server import app
from server.models import db, User

from server.controllers import auth_module
from server.services.auth import (
    google_oauth_provider,
    is_google_login_enabled,
    oauth_provider,
)


def _canvas_authorize():
    return oauth_provider.authorize(
        callback=url_for('auth.authorized', state=None, _external=True, _scheme="https"))


@auth_module.route('/login/')
def login():
    if canvas_client.is_mock_canvas():
        return redirect(url_for('dev_login.dev_login_page'))
    if is_google_login_enabled():
        # Show a chooser so users can pick between Canvas and Google.
        return render_template(
            'login.html.j2',
            title="Login",
            google_enabled=True,
        )
    return _canvas_authorize()


@auth_module.route('/login/canvas/')
def login_canvas():
    if canvas_client.is_mock_canvas():
        return redirect(url_for('dev_login.dev_login_page'))
    return _canvas_authorize()


@auth_module.route('/authorized/')
def authorized():
    resp = oauth_provider.authorized_response()
    if resp is None:
        return 'Access denied: {}'.format(request.args.get('error', 'unknown error'))
    session['access_token'] = resp['access_token']
    user_info = resp['user']

    user = canvas_client.get_user(user_info['id'])
    staff_course_dics, student_course_dics, _, _ = canvas_client.get_user_courses_categorized(user)
    staff_offerings = [str(c.id) for c in staff_course_dics]
    student_offerings = [str(c.id) for c in student_course_dics]

    email = user_info.get('email') or getattr(user, 'email', None)

    user_model = User.query.filter_by(canvas_id=str(user_info['id'])).one_or_none()
    if not user_model:
        user_model = User(
            name=user_info['name'],
            canvas_id=str(user_info['id']),
            email=email,
            staff_offerings=staff_offerings,
            student_offerings=student_offerings)
        db.session.add(user_model)
    else:
        user_model.staff_offerings = staff_offerings
        user_model.student_offerings = student_offerings
        if email:
            user_model.email = email
    db.session.commit()

    login_user(user_model, remember=True)
    after_login = session.pop('after_login', None) or url_for('index')
    return redirect(after_login)


@auth_module.route('/login/google/')
def login_google():
    if not is_google_login_enabled():
        flash("Google login is not configured for this server.", "error")
        return redirect(url_for('index'))
    return google_oauth_provider.authorize(
        callback=url_for('auth.authorized_google', _external=True, _scheme="https"))


def _google_profile_from_response(resp):
    """Validate the token response and fetch the user's Google profile."""
    if resp is None or 'access_token' not in resp:
        return None, 'Access denied: {}'.format(request.args.get('error', 'unknown error'))
    session['google_access_token'] = resp['access_token']
    profile_resp = google_oauth_provider.get('userinfo')
    profile = profile_resp.data if profile_resp else None
    if not profile or not isinstance(profile, dict):
        flash("Could not read Google profile.", "error")
        return None, redirect(url_for('index'))
    if not profile.get('email_verified', True):
        flash("Your Google email is not verified.", "error")
        return None, redirect(url_for('index'))
    return profile, None


def _google_domain_is_allowed(profile):
    allowed_domains = [
        d.strip().lower()
        for d in (app.config.get('GOOGLE_HOSTED_DOMAINS') or '').split(',')
        if d.strip()
    ]
    if not allowed_domains:
        return True
    email = (profile.get('email') or '').lower().strip()
    hd = (profile.get('hd') or email.rsplit('@', 1)[-1]).lower()
    return hd in allowed_domains


def _find_existing_user_for_google(google_id, email):
    user_model = User.query.filter_by(google_id=google_id).one_or_none()
    if not user_model:
        user_model = User.query.filter(db.func.lower(User.email) == email).one_or_none()
    return user_model


@auth_module.route('/authorized/google/')
def authorized_google():
    """Authenticate an existing user via their Google account.

    This handler intentionally does NOT create new users — Google OAuth is
    only a sign-in alternative for users that already exist in the system
    (typically created on first Canvas login). Unknown emails are rejected.
    """
    if not is_google_login_enabled():
        flash("Google login is not configured for this server.", "error")
        return redirect(url_for('index'))

    profile, early_response = _google_profile_from_response(
        google_oauth_provider.authorized_response())
    if profile is None:
        return early_response

    email = (profile.get('email') or '').lower().strip()
    google_id = profile.get('sub')
    if not email or not google_id:
        flash("Google did not return an email address.", "error")
        return redirect(url_for('index'))

    if not _google_domain_is_allowed(profile):
        flash("Your Google domain is not permitted to sign in here.", "error")
        return redirect(url_for('index'))

    user_model = _find_existing_user_for_google(google_id, email)
    if not user_model:
        flash(
            "No account is associated with this Google email. "
            "Please log in with Canvas at least once first.",
            "error")
        return redirect(url_for('index'))

    # Link the Google identity on first successful match so subsequent
    # logins are bound by the stable Google subject id, not just email.
    if not user_model.google_id:
        user_model.google_id = google_id
        db.session.commit()

    login_user(user_model, remember=True)
    after_login = session.pop('after_login', None) or url_for('index')
    return redirect(after_login)


@auth_module.route('/logout/')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('index'))
